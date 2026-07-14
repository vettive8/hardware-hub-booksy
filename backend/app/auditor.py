from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Severity = Literal["critical", "high", "medium", "low"]
AUDITOR_INSTRUCTIONS = """You are an additive inventory reviewer. Inspect accepted inventory and rejected/flagged seed-import evidence. Return one JSON object with a `findings` array. Each finding must use only evidence supplied here and contain code, severity (critical, high, medium, or low), hardware_id (an ID present in the supplied source or null), title, explanation, and evidence as a short text quote or fact from the supplied data. Look for contradictions or safety concerns not already obvious. Never claim the inventory is clean and never invent identifiers or facts."""

# Provider grammars support a smaller JSON Schema subset than Pydantic. Keep this
# deliberately boring and portable; LLMAuditResponse remains the richer trust boundary.
WIRE_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Lowercase snake_case finding category."},
                    "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "hardware_id": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}],
                        "description": "An identifier present in the supplied source, or null.",
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

    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_]+$")
    severity: Severity
    hardware_id: int | None = None
    title: str = Field(min_length=2, max_length=160)
    explanation: str = Field(min_length=2, max_length=1000)
    evidence: str = Field(min_length=2, max_length=500)


class LLMAuditResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[LLMFinding] = Field(max_length=50)


@dataclass(frozen=True)
class ProviderAuditResult:
    payload: dict[str, Any]
    model: str


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


def source_hardware_ids(evidence: dict[str, list[dict[str, Any]]]) -> set[int]:
    ids = {item["id"] for item in evidence["inventory"] if isinstance(item.get("id"), int)}
    ids.update(
        issue["hardware_id"]
        for issue in evidence["import_issues"]
        if isinstance(issue.get("hardware_id"), int)
    )
    return ids


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
                "evidence": {
                    "source_index": issue["source_index"],
                    "name": raw.get("name"),
                    "status": raw.get("status"),
                    "purchase_date": raw.get("purchaseDate"),
                    "notes": raw.get("notes") or raw.get("history"),
                },
                "source": "rules",
            }
        )
    return findings


def request_llm_audit(evidence: dict[str, list[dict[str, Any]]]) -> ProviderAuditResult:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
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
            "json_schema": {
                "name": "inventory_audit",
                "strict": True,
                "schema": WIRE_AUDIT_SCHEMA,
            },
        },
        extra_body=routing,
        messages=[
            {"role": "system", "content": AUDITOR_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
        ],
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("OpenRouter returned an empty audit")
    return ProviderAuditResult(payload=json.loads(content), model=completion.model)


def merge_findings(
    rule_findings: list[dict[str, Any]],
    llm_response: LLMAuditResponse,
    valid_ids: set[int],
) -> tuple[list[dict[str, Any]], int, int]:
    merged = list(rule_findings)
    occupied = {(item["hardware_id"], item["code"]) for item in rule_findings}
    unknown_id_drops = 0
    duplicate_drops = 0
    for validated in llm_response.findings:
        finding = validated.model_dump()
        if finding["hardware_id"] is not None and finding["hardware_id"] not in valid_ids:
            unknown_id_drops += 1
            continue
        key = (finding["hardware_id"], finding["code"])
        if key in occupied:
            duplicate_drops += 1
            continue
        finding["source"] = "llm"
        merged.append(finding)
        occupied.add(key)
    return merged, unknown_id_drops, duplicate_drops


def run_audit(db: sqlite3.Connection) -> dict[str, Any]:
    evidence = collect_evidence(db)
    rule_findings = deterministic_findings(evidence)
    findings = rule_findings
    primary = os.getenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    llm_status = {
        "state": "not_configured",
        "message": "Deterministic rules ran; add OPENROUTER_API_KEY for an additive model review.",
        "accepted_findings": 0,
    }
    guard = {"dropped_unknown_ids": 0, "dropped_rule_duplicates": 0}
    mode = "rules"

    if os.getenv("OPENROUTER_API_KEY"):
        try:
            provider_result = request_llm_audit(evidence)
            validated = LLMAuditResponse.model_validate(provider_result.payload)
            findings, unknown_drops, duplicate_drops = merge_findings(
                rule_findings, validated, source_hardware_ids(evidence)
            )
            guard = {"dropped_unknown_ids": unknown_drops, "dropped_rule_duplicates": duplicate_drops}
            llm_status = {
                "state": "succeeded",
                "message": "Model findings passed provider and application schemas, ID checks, and rule-first deduplication.",
                "accepted_findings": len(findings) - len(rule_findings),
            }
            primary = provider_result.model
            mode = "rules+llm"
        except ValidationError as exc:
            llm_status = {
                "state": "invalid_response",
                "message": f"Model layer discarded after schema validation failed ({exc.error_count()} errors).",
                "accepted_findings": 0,
            }
            mode = "rules-fallback"
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
        "model": primary if os.getenv("OPENROUTER_API_KEY") else None,
        "summary": {"total": len(findings), "rule_findings": len(rule_findings), **counts},
        "findings": findings,
        "llm_status": llm_status,
        "hallucination_guard": guard,
    }
