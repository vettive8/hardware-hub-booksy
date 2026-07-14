from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import admin_user, create_access_token, current_user, ensure_default_users, hash_password, verify_password
from .database import get_db, initialize_database
from .schemas import HardwareOut, LoginRequest, UserCreate
from .seed import ensure_seeded


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

