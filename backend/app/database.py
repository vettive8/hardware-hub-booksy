from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT_DIR / "hardware_hub.db"


def database_path() -> Path:
    return Path(os.getenv("DATABASE_PATH", DEFAULT_DB_PATH))


def connect(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(path or database_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path | None = None) -> None:
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS hardware (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                brand TEXT NOT NULL,
                serial_number TEXT,
                category TEXT CHECK (category IN ('Laptop', 'Mobile', 'Tablet', 'Monitor', 'Accessory')),
                purchase_date TEXT,
                status TEXT NOT NULL CHECK (status IN ('Available', 'In Use', 'Repair')),
                notes TEXT,
                history TEXT,
                assigned_to TEXT,
                is_damaged INTEGER NOT NULL DEFAULT 0 CHECK (is_damaged IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS rentals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hardware_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rented_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                returned_at TEXT,
                FOREIGN KEY (hardware_id) REFERENCES hardware(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE UNIQUE INDEX IF NOT EXISTS one_active_rental_per_item
                ON rentals(hardware_id) WHERE returned_at IS NULL;

            CREATE TABLE IF NOT EXISTS import_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_index INTEGER NOT NULL,
                hardware_id INTEGER,
                code TEXT NOT NULL,
                severity TEXT NOT NULL CHECK (severity IN ('warning', 'error')),
                message TEXT NOT NULL,
                raw_record TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # CREATE TABLE IF NOT EXISTS never alters an existing table, so databases
        # created before serial_number/category existed need the columns added here.
        existing = {row["name"] for row in db.execute("PRAGMA table_info(hardware)")}
        if "serial_number" not in existing:
            db.execute("ALTER TABLE hardware ADD COLUMN serial_number TEXT")
        if "category" not in existing:
            db.execute(
                "ALTER TABLE hardware ADD COLUMN category TEXT "
                "CHECK (category IN ('Laptop', 'Mobile', 'Tablet', 'Monitor', 'Accessory'))"
            )
        # The index depends on serial_number, so it can only exist after the migration.
        db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS unique_serial_number "
            "ON hardware(serial_number) WHERE serial_number IS NOT NULL"
        )


def get_db() -> Generator[sqlite3.Connection, None, None]:
    db = connect()
    try:
        yield db
    finally:
        db.close()

