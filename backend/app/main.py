from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import admin_user, create_access_token, current_user, ensure_default_users, hash_password, verify_password
from .auditor import run_audit
from .database import get_db, initialize_database
from .schemas import HardwareCreate, HardwareOut, LoginRequest, UserCreate
from .seed import DAMAGE_TERMS, ensure_seeded


def serialize_hardware(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["is_damaged"] = bool(item["is_damaged"])
    return item


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    ensure_default_users()
    ensure_seeded()
    yield


app = FastAPI(
    title="Hardware Hub API",
    description="Safe hardware rental management with an explainable inventory auditor.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Annotated[sqlite3.Connection, Depends(get_db)]) -> dict:
    user = db.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (str(payload.email),)).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }


@app.get("/api/auth/me")
def me(user: Annotated[sqlite3.Row, Depends(current_user)]) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}


@app.get("/api/hardware", response_model=list[HardwareOut])
def list_hardware(
    _: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    brand: str | None = None,
    search: str | None = None,
    sort: Literal["name", "brand", "purchase_date", "status"] = "name",
    direction: Literal["asc", "desc"] = "asc",
) -> list[dict]:
    clauses: list[str] = []
    params: list[str] = []
    if status_filter:
        clauses.append("status = ?")
        params.append(status_filter)
    if brand:
        clauses.append("brand = ? COLLATE NOCASE")
        params.append(brand)
    if search:
        clauses.append("(name LIKE ? OR brand LIKE ? OR COALESCE(notes, '') LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    order_columns = {"name": "name", "brand": "brand", "purchase_date": "purchase_date", "status": "status"}
    sql = "SELECT * FROM hardware"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY {order_columns[sort]} {direction.upper()}, id ASC"
    return [serialize_hardware(row) for row in db.execute(sql, params).fetchall()]


@app.get("/api/users")
def list_users(
    _: Annotated[sqlite3.Row, Depends(admin_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[dict]:
    rows = db.execute("SELECT id, name, email, role, created_at FROM users ORDER BY name").fetchall()
    return [dict(row) for row in rows]


@app.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    _: Annotated[sqlite3.Row, Depends(admin_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    try:
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (payload.name.strip(), str(payload.email).lower(), hash_password(payload.password), payload.role),
        )
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists") from None
    return {"id": cursor.lastrowid, "name": payload.name.strip(), "email": str(payload.email).lower(), "role": payload.role}


@app.post("/api/hardware", response_model=HardwareOut, status_code=status.HTTP_201_CREATED)
def create_hardware(
    payload: HardwareCreate,
    _: Annotated[sqlite3.Row, Depends(admin_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    purchase_date = payload.purchase_date
    if purchase_date:
        try:
            parsed = date.fromisoformat(purchase_date)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Purchase date must be ISO YYYY-MM-DD") from None
        if parsed > date.today():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Purchase date cannot be in the future")
    is_damaged = any(term in (payload.notes or "").casefold() for term in DAMAGE_TERMS)
    next_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS id FROM hardware").fetchone()["id"]
    db.execute(
        """
        INSERT INTO hardware (id, name, brand, purchase_date, status, notes, is_damaged)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (next_id, payload.name.strip(), payload.brand.strip(), purchase_date, payload.status, payload.notes, int(is_damaged)),
    )
    db.commit()
    row = db.execute("SELECT * FROM hardware WHERE id = ?", (next_id,)).fetchone()
    return serialize_hardware(row)


@app.delete(
    "/api/hardware/{hardware_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_hardware(
    hardware_id: int,
    _: Annotated[sqlite3.Row, Depends(admin_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> Response:
    item = db.execute("SELECT status FROM hardware WHERE id = ?", (hardware_id,)).fetchone()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hardware not found")
    if item["status"] == "In Use":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Return the hardware before deleting it")
    db.execute("DELETE FROM hardware WHERE id = ?", (hardware_id,))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.patch("/api/hardware/{hardware_id}/repair", response_model=HardwareOut)
def toggle_repair(
    hardware_id: int,
    _: Annotated[sqlite3.Row, Depends(admin_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    item = db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hardware not found")
    if item["status"] == "In Use":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Return the hardware before sending it to repair")
    if item["status"] == "Repair":
        next_status, damaged = "Available", 0
    else:
        next_status, damaged = "Repair", item["is_damaged"]
    db.execute("UPDATE hardware SET status = ?, is_damaged = ? WHERE id = ?", (next_status, damaged, hardware_id))
    db.commit()
    return serialize_hardware(db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone())


@app.post("/api/hardware/{hardware_id}/rent", response_model=HardwareOut)
def rent_hardware(
    hardware_id: int,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    db.execute("BEGIN IMMEDIATE")
    item = db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone()
    if not item:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hardware not found")
    if item["is_damaged"]:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Damaged hardware cannot be rented")
    if item["status"] != "Available":
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Hardware is {item['status']} and cannot be rented")
    updated = db.execute(
        "UPDATE hardware SET status = 'In Use', assigned_to = ? WHERE id = ? AND status = 'Available' AND is_damaged = 0",
        (user["email"], hardware_id),
    )
    if updated.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Hardware became unavailable; refresh and try again")
    db.execute("INSERT INTO rentals (hardware_id, user_id) VALUES (?, ?)", (hardware_id, user["id"]))
    db.commit()
    return serialize_hardware(db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone())


@app.post("/api/hardware/{hardware_id}/return", response_model=HardwareOut)
def return_hardware(
    hardware_id: int,
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    db.execute("BEGIN IMMEDIATE")
    item = db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone()
    if not item:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hardware not found")
    if item["status"] != "In Use":
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only hardware currently In Use can be returned")
    if user["role"] != "admin" and item["assigned_to"] != user["email"]:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only return hardware assigned to you")
    next_status = "Repair" if item["is_damaged"] else "Available"
    db.execute("UPDATE hardware SET status = ?, assigned_to = NULL WHERE id = ?", (next_status, hardware_id))
    db.execute(
        "UPDATE rentals SET returned_at = CURRENT_TIMESTAMP WHERE hardware_id = ? AND returned_at IS NULL",
        (hardware_id,),
    )
    db.commit()
    return serialize_hardware(db.execute("SELECT * FROM hardware WHERE id = ?", (hardware_id,)).fetchone())


@app.get("/api/rentals/mine")
def my_rentals(
    user: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> list[dict]:
    rows = db.execute(
        """
        SELECT r.id AS rental_id, r.rented_at, h.*
        FROM rentals r JOIN hardware h ON h.id = r.hardware_id
        WHERE r.user_id = ? AND r.returned_at IS NULL
        ORDER BY r.rented_at DESC
        """,
        (user["id"],),
    ).fetchall()
    return [{**serialize_hardware(row), "rental_id": row["rental_id"], "rented_at": row["rented_at"]} for row in rows]


@app.post("/api/audit")
def audit_inventory(
    _: Annotated[sqlite3.Row, Depends(current_user)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    return run_audit(db)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
