from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .database import ROOT_DIR, connect, initialize_database

VALID_STATUSES = {"Available", "In Use", "Repair"}
DAMAGE_TERMS = ("damage", "swelling", "sticky", "broken", "cracked", "do not issue")


@dataclass(frozen=True)
class ImportIssue:
    source_index: int
    hardware_id: int | None
    code: str
    severity: str
    message: str
    raw_record: str


@dataclass(frozen=True)
class ImportReport:
    inserted: int
    rejected: int
    issues: list[ImportIssue]

    def as_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "rejected": self.rejected,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _issue(index: int, record: dict[str, Any], code: str, severity: str, message: str) -> ImportIssue:
    raw_id = record.get("id")
    return ImportIssue(
        source_index=index,
        hardware_id=raw_id if isinstance(raw_id, int) else None,
        code=code,
        severity=severity,
        message=message,
        raw_record=json.dumps(record, ensure_ascii=False),
    )


def _parse_date(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, "Purchase date is missing"
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None, f"Purchase date {value!r} is not ISO YYYY-MM-DD"
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None, f"Purchase date {value!r} is not a real calendar date"
    return parsed.isoformat(), None


def load_seed(seed_path: Path | None = None, db_path: Path | None = None, *, reset: bool = False) -> ImportReport:
    path = seed_path or ROOT_DIR / "data" / "inventory.seed.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Seed root must be a JSON array")

    initialize_database(db_path)
    issues: list[ImportIssue] = []
    inserted = 0
    rejected = 0
    seen_ids: set[int] = set()

    with connect(db_path) as db:
        if reset:
            db.execute("DELETE FROM rentals")
            db.execute("DELETE FROM hardware")
            db.execute("DELETE FROM import_issues")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                issue = ImportIssue(index, None, "invalid_record", "error", "Record must be an object", json.dumps(record))
                issues.append(issue)
                rejected += 1
                continue

            hardware_id = record.get("id")
            row_issues: list[ImportIssue] = []
            fatal = False

            if not isinstance(hardware_id, int):
                row_issues.append(_issue(index, record, "invalid_id", "error", "ID must be an integer"))
                fatal = True
            elif hardware_id in seen_ids:
                row_issues.append(_issue(index, record, "duplicate_id", "error", f"Duplicate hardware id {hardware_id}; record rejected"))
                fatal = True
            else:
                seen_ids.add(hardware_id)

            name = record.get("name")
            brand = record.get("brand")
            status = record.get("status")
            if not isinstance(name, str) or not name.strip():
                row_issues.append(_issue(index, record, "missing_name", "error", "Hardware name is required"))
                fatal = True
            if not isinstance(brand, str) or not brand.strip():
                row_issues.append(_issue(index, record, "missing_brand", "error", "Brand is required"))
                fatal = True
            elif brand.casefold() == "appel":
                row_issues.append(_issue(index, record, "brand_typo", "warning", "Brand 'Appel' may be a typo for 'Apple'"))
            if status not in VALID_STATUSES:
                row_issues.append(_issue(index, record, "unknown_status", "error", f"Unsupported status {status!r}"))
                fatal = True

            parsed_date, date_error = _parse_date(record.get("purchaseDate"))
            if date_error:
                row_issues.append(_issue(index, record, "invalid_purchase_date", "error", date_error))
                fatal = True
            elif parsed_date and date.fromisoformat(parsed_date) > date.today():
                row_issues.append(_issue(index, record, "future_purchase_date", "warning", f"Purchase date {parsed_date} is in the future"))

            safety_text = " ".join(str(record.get(field, "")) for field in ("notes", "history")).casefold()
            is_damaged = any(term in safety_text for term in DAMAGE_TERMS)
            if is_damaged:
                row_issues.append(
                    _issue(index, record, "damage_status_conflict", "error", "Damage language conflicts with the record's operational status")
                )

            issues.extend(row_issues)
            if fatal:
                rejected += 1
                continue

            try:
                db.execute(
                    """
                    INSERT INTO hardware (id, name, brand, purchase_date, status, notes, history, assigned_to, is_damaged)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        hardware_id,
                        name.strip(),
                        brand.strip(),
                        parsed_date,
                        status,
                        record.get("notes"),
                        record.get("history"),
                        record.get("assignedTo"),
                        int(is_damaged),
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError as exc:
                issues.append(_issue(index, record, "database_conflict", "error", f"Database rejected record: {exc}"))
                rejected += 1

        db.executemany(
            """
            INSERT INTO import_issues (source_index, hardware_id, code, severity, message, raw_record)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(i.source_index, i.hardware_id, i.code, i.severity, i.message, i.raw_record) for i in issues],
        )

    return ImportReport(inserted=inserted, rejected=rejected, issues=issues)


def ensure_seeded(seed_path: Path | None = None, db_path: Path | None = None) -> ImportReport | None:
    initialize_database(db_path)
    with connect(db_path) as db:
        count = db.execute("SELECT COUNT(*) AS count FROM hardware").fetchone()["count"]
    return None if count else load_seed(seed_path, db_path)

