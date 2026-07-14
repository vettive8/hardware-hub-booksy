"""AI Inventory Auditor.

Two independent passes inspect the same source data.

The deterministic rule engine is the safety authority. It always runs, costs
nothing, and its findings can never be removed or downgraded by the model.

The language model runs a second, independent pass. It is shown the evidence --
accepted inventory plus the raw source rows -- but never the loader's conclusions,
so it cannot simply restate them. Agreement between the two passes is recorded as
corroboration rather than discarded as duplication:

    corroborated  both passes found it          highest confidence
    rules_only    provable; the model missed it  tells us where the model is weak
    model_only    the model alone raised it      the signal we are paying for

Model output is untrusted input. Each finding is validated on its own, and a bad
finding is quarantined without discarding the valid ones -- the same policy the
seed loader applies to bad records.
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Severity = Literal["critical", "high", "medium", "low"]

# A shared taxonomy, not an answer key. The model is told which *kinds* of problem
# exist so its findings can be compared with the rule engine's; it is never told
# which records have them. `other` is the escape hatch for genuinely novel findings,
# which by definition can never corroborate a rule.
FindingCode = Literal[
    "duplicate_id",
    "invalid_id",
    "missing_name",
    "missing_brand",
    "brand_typo",
    "unknown_status",
    "invalid_purchase_date",
    "future_purchase_date",
    "damage_status_conflict",
    "database_conflict",
    "other",
]
FINDING_CODES: list[str] = list(FindingCode.__args__)

AUDITOR_INSTRUCTIONS = """You are an independent inventory auditor for a hardware rental system.

You receive two things:
- `accepted_inventory`: the records that were loaded into the operational database.
- `raw_source_rows`: rows exactly as they appeared in the supplied source file. Some of
  these were never loaded. Work out for yourself which ones are unsafe, and why.

Nobody has told you what is wrong with this data. Determine it from the evidence.
Look for colliding identifiers, impossible or implausible dates, misspelled brands,
unsupported statuses, missing required fields, and free-text notes or history that
contradict a record's declared status.

Rules:
- Use only the evidence supplied. Never invent an identifier, a record, or a fact.
- `hardware_id` must be the `id` field of the row the finding is about -- including
  rows that were never loaded, which still carry an `id`. Use null only for an
  observation about the file as a whole, never as a substitute for an id you can see.
- Raise one finding per problem per row. Do not restate the same problem twice.
- Choose the `code` that best classifies the problem. Use `other` only for a real
  problem that none of the listed codes describe.
- `evidence` must be a short, literal quote or fact drawn from the supplied data.
- Never claim the inventory is clean."""

# Provider grammars support a smaller JSON Schema subset than Pydantic. Keep this
# deliberately boring and portable; LLMAuditResponse remains the trust boundary.
WIRE_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "enum": FINDING_CODES},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "hardware_id": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "An identifier present in the supplied data, or null.",
                    },
                    "title": {"type": "string"},
                    "explanation": {"type": "string"},
                    "evidence": {"type": "string", "description": "A short quote or fact from supplied data."},
                },
                "required": ["code", "severity", "hardware_id", "title", "explanation", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}

TITLE_BY_CODE = {
    "duplicate_id": "Duplicate identifier rejected",
    "future_purchase_date": "Purchase date is in the future",
    "brand_typo": "Likely brand typo",
    "invalid_purchase_date": "Non-standard purchase date",
    "missing_brand": "Brand is missing",
    "unknown_status": "Unsupported inventory status",
    "damage_status_conflict": "Available item contains damage evidence",
    "invalid_id": "Invalid hardware identifier",
    "missing_name": "Hardware name is missing",
    "database_conflict": "Database constraint rejected a record",
}


class LLMFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: FindingCode
    severity: Severity
    hardware_id: int | None = None
    title: str = Field(min_length=2, max_length=160)
    explanation: str = Field(min_length=2, max_length=1000)
    evidence: str = Field(min_length=2, max_length=500)


@dataclass(frozen=True)
class ProviderAuditResult:
    payload: dict[str, Any]
    model: str


def openrouter_enabled() -> bool:
    disabled = os.getenv("OPENROUTER_DISABLED", "").strip().casefold() in {"1", "true", "yes"}
    return bool(os.getenv("OPENROUTER_API_KEY")) and not disabled


def _severity(code: str, imported_severity: str) -> Severity:
    if code == "damage_status_conflict":
        return "critical"
    if code in {"duplicate_id", "unknown_status", "database_conflict"}:
        return "high"
    if code in {"future_purchase_date", "invalid_purchase_date", "missing_brand"}:
        return "medium"
    return "medium" if imported_severity == "error" else "low"


def collect_evidence(db: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    inventory = [dict(row) for row in db.execute("SELECT * FROM hardware ORDER BY id").fetchall()]
    for item in inventory:
        item["is_damaged"] = bool(item["is_damaged"])
    import_issues = [
        dict(row)
        for row in db.execute(
            "SELECT source_index, hardware_id, code, severity, message, raw_record FROM import_issues ORDER BY id"
        ).fetchall()
    ]
    return {"inventory": inventory, "import_issues": import_issues}


def model_evidence(evidence: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The payload sent to the model: evidence without the loader's conclusions.

    Sending `import_issues` verbatim would hand the model the rule engine's own
    codes and messages, which it would restate. Sending only the accepted inventory
    would go too far the other way -- rejected records never reach the hardware
    table, so the model would be blind to the duplicate ID, the unknown status and
    the unparseable date. The raw source rows carry the evidence without the answer.
    """
    seen: set[int] = set()
    raw_rows: list[dict[str, Any]] = []
    for issue in evidence["import_issues"]:
        index = issue["source_index"]
        if index in seen:
            continue
        seen.add(index)
        raw_rows.append({"source_index": index, "row": json.loads(issue["raw_record"])})
    return {
        "accepted_inventory": evidence["inventory"],
        "raw_source_rows": sorted(raw_rows, key=lambda item: item["source_index"]),
    }


def source_hardware_ids(evidence: dict[str, list[dict[str, Any]]]) -> set[int]:
    ids = {item["id"] for item in evidence["inventory"] if isinstance(item.get("id"), int)}
    ids.update(
        issue["hardware_id"]
        for issue in evidence["import_issues"]
        if isinstance(issue.get("hardware_id"), int)
    )
    return ids


def _rule_evidence_line(raw: dict[str, Any], source_index: int) -> str:
    notes = raw.get("notes") or raw.get("history")
    parts = [
        f"source row {source_index}",
        str(raw.get("name") or "unnamed record"),
        f"brand {raw.get('brand') or 'none'}",
        f"status {raw.get('status') or 'none'}",
        f"purchased {raw.get('purchaseDate') or 'none'}",
    ]
    if notes:
        parts.append(f"notes: {notes}")
    return " · ".join(parts)[:500]


def deterministic_findings(evidence: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    findings = []
    for issue in evidence["import_issues"]:
        code = issue["code"]
        raw = json.loads(issue["raw_record"])
        findings.append(
            {
                "code": code,
                "severity": _severity(code, issue["severity"]),
                "hardware_id": issue["hardware_id"],
                "title": TITLE_BY_CODE.get(code, "Inventory import anomaly"),
                "explanation": issue["message"],
                "evidence": _rule_evidence_line(raw, issue["source_index"]),
                "source": "rules",
                "confidence": "rules_only",
            }
        )
    return findings


def request_llm_audit(evidence: dict[str, list[dict[str, Any]]]) -> ProviderAuditResult:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not openrouter_enabled():
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    primary = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    configured_fallbacks = os.getenv("OPENROUTER_FALLBACK_MODELS", "google/gemini-3.1-flash-lite")
    fallbacks = [model.strip() for model in configured_fallbacks.split(",") if model.strip() and model.strip() != primary]
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key, timeout=45.0)
    routing: dict[str, Any] = {"provider": {"require_parameters": True}}
    if fallbacks:
        routing["models"] = fallbacks
    completion = client.chat.completions.create(
        model=primary,
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "inventory_audit", "strict": True, "schema": WIRE_AUDIT_SCHEMA},
        },
        extra_body=routing,
        messages=[
            {"role": "system", "content": AUDITOR_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(model_evidence(evidence), ensure_ascii=False)},
        ],
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("OpenRouter returned an empty audit")
    return ProviderAuditResult(payload=json.loads(content), model=completion.model)


def validate_findings(payload: Any) -> tuple[list[LLMFinding], int]:
    """Quarantine bad findings individually; never discard the batch for one bad row.

    Raises only when the envelope itself is unusable, which is the one case where
    there is nothing left to salvage.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        raise ValueError("Model response has no usable findings array")

    accepted: list[LLMFinding] = []
    dropped = 0
    for raw in payload["findings"][:50]:
        try:
            accepted.append(LLMFinding.model_validate(raw))
        except ValidationError:
            dropped += 1
    return accepted, dropped


def merge_findings(
    rule_findings: list[dict[str, Any]],
    llm_findings: list[LLMFinding],
    valid_ids: set[int],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Rules stay authoritative. Agreement is corroboration, not duplication."""
    rule_keys = {(item["hardware_id"], item["code"]) for item in rule_findings}
    corroborated_keys: set[tuple[int | None, str]] = set()
    model_only: list[dict[str, Any]] = []
    dropped_unknown_ids = 0

    for validated in llm_findings:
        finding = validated.model_dump()
        if finding["hardware_id"] is not None and finding["hardware_id"] not in valid_ids:
            dropped_unknown_ids += 1
            continue
        key = (finding["hardware_id"], finding["code"])
        if key in rule_keys:
            corroborated_keys.add(key)
            continue
        finding["source"] = "llm"
        finding["confidence"] = "model_only"
        model_only.append(finding)

    merged: list[dict[str, Any]] = []
    for item in rule_findings:
        promoted = dict(item)
        key = (item["hardware_id"], item["code"])
        promoted["confidence"] = "corroborated" if key in corroborated_keys else "rules_only"
        merged.append(promoted)
    merged.extend(model_only)

    counts = {
        "corroborated": len(corroborated_keys),
        "rules_only": len(rule_findings) - len(corroborated_keys),
        "model_only": len(model_only),
        "dropped_unknown_ids": dropped_unknown_ids,
    }
    return merged, counts


def run_audit(db: sqlite3.Connection) -> dict[str, Any]:
    evidence = collect_evidence(db)
    rule_findings = deterministic_findings(evidence)
    findings = rule_findings
    primary = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    llm_status = {
        "state": "not_configured",
        "message": "Deterministic rules ran; add OPENROUTER_API_KEY for an independent model pass.",
        "accepted_findings": 0,
    }
    guard = {
        "corroborated": 0,
        "rules_only": len(rule_findings),
        "model_only": 0,
        "dropped_unknown_ids": 0,
        "dropped_invalid_schema": 0,
    }
    mode = "rules"

    if os.getenv("OPENROUTER_API_KEY") and not openrouter_enabled():
        llm_status = {
            "state": "disabled",
            "message": "OPENROUTER_DISABLED is set; the paid provider call was skipped.",
            "accepted_findings": 0,
        }
    elif openrouter_enabled():
        try:
            provider_result = request_llm_audit(evidence)
            validated, dropped_invalid = validate_findings(provider_result.payload)
            findings, counts = merge_findings(rule_findings, validated, source_hardware_ids(evidence))
            guard = {**counts, "dropped_invalid_schema": dropped_invalid}
            llm_status = {
                "state": "succeeded",
                "message": (
                    f"Independent model pass: {counts['model_only']} new findings, "
                    f"{counts['corroborated']} corroborating the rule engine."
                ),
                "accepted_findings": counts["model_only"],
            }
            primary = provider_result.model
            mode = "rules+llm"
        except (APIError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError, RuntimeError) as exc:
            llm_status = {
                "state": "failed",
                "message": f"Model layer failed safely ({type(exc).__name__}); deterministic findings remain complete.",
                "accepted_findings": 0,
            }
            mode = "rules-fallback"

    counts = {
        level: sum(1 for item in findings if item.get("severity") == level)
        for level in ("critical", "high", "medium", "low")
    }
    return {
        "mode": mode,
        "model": primary if openrouter_enabled() else None,
        "summary": {"total": len(findings), "rule_findings": len(rule_findings), **counts},
        "findings": findings,
        "llm_status": llm_status,
        "hallucination_guard": guard,
    }
