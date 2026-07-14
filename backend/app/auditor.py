from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

import httpx

AUDITOR_INSTRUCTIONS = """You are an inventory safety auditor. Inspect both accepted inventory rows and rejected/flagged seed-import evidence. Return JSON only with a top-level `findings` array. Each finding must have code, severity (critical, high, medium, or low), hardware_id (integer or null), title, explanation, and evidence. Detect duplicate identifiers, invalid/future dates, misspelled or blank brands, unsupported statuses, and contradictions where an item is Available despite notes/history indicating damage. Do not invent missing evidence."""

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


def _severity(code: str, imported_severity: str) -> str:
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
                "source": "deterministic",
            }
        )
    return findings


def _extract_response_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks)


def llm_findings(evidence: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
            "instructions": AUDITOR_INSTRUCTIONS,
            "input": json.dumps(evidence, ensure_ascii=False),
        },
        timeout=45,
    )
    response.raise_for_status()
    parsed = json.loads(_extract_response_text(response.json()))
    findings = parsed.get("findings")
    if not isinstance(findings, list):
        raise ValueError("LLM response did not contain a findings array")
    for finding in findings:
        finding["source"] = "llm"
    return findings


def run_audit(db: sqlite3.Connection) -> dict[str, Any]:
    evidence = collect_evidence(db)
    local_findings = deterministic_findings(evidence)
    mode = "local"
    fallback_reason = None
    findings = local_findings

    if os.getenv("OPENAI_API_KEY"):
        try:
            findings = llm_findings(evidence)
            mode = "openai"
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError, RuntimeError) as exc:
            mode = "local-fallback"
            fallback_reason = f"Live audit failed safely: {type(exc).__name__}"

    counts = {level: sum(1 for item in findings if item.get("severity") == level) for level in ("critical", "high", "medium", "low")}
    return {
        "mode": mode,
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini") if mode == "openai" else None,
        "summary": {"total": len(findings), **counts},
        "findings": findings,
        "fallback_reason": fallback_reason,
    }

