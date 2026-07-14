from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .database import connect, get_db

ALGORITHM = "HS256"
TOKEN_TTL_MINUTES = 8 * 60
DEVELOPMENT_SECRET = "local-development-secret-change-me"
passwords = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().casefold() == "production"


def demo_mode() -> bool:
    """Seeded demo accounts. Off by default in production, on everywhere else."""
    configured = os.getenv("DEMO_MODE")
    if configured is None:
        return not is_production()
    return configured.strip().casefold() in {"1", "true", "yes"}


def secret_key() -> str:
    """A public demo is still production. The two controls are independent: DEMO_MODE
    decides whether demo accounts exist, APP_ENV decides whether a real secret is
    mandatory. A deployed instance signing tokens with a secret published in a public
    repository would let anyone forge an admin session.
    """
    key = os.getenv("SECRET_KEY", DEVELOPMENT_SECRET)
    if is_production() and key == DEVELOPMENT_SECRET:
        raise RuntimeError("APP_ENV=production requires SECRET_KEY to be set to a real secret")
    return key


def hash_password(password: str) -> str:
    return passwords.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return passwords.verify(password, password_hash)


def create_access_token(user: sqlite3.Row) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return jwt.encode(payload, secret_key(), algorithm=ALGORITHM)


def ensure_default_users(db_path=None) -> None:
    if not demo_mode():
        return
    defaults = (
        ("Admin User", "admin@booksy.com", "Admin123!", "admin"),
        ("Demo Member", "member@booksy.com", "Member123!", "user"),
        ("John Doe", "j.doe@booksy.com", "Member123!", "user"),
    )
    with connect(db_path) as db:
        for name, email, password, role in defaults:
            db.execute(
                "INSERT OR IGNORE INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                (name, email, hash_password(password), role),
            )


def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[sqlite3.Connection, Depends(get_db)],
) -> sqlite3.Row:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, secret_key(), algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise unauthorized from None
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        raise unauthorized
    return user


def admin_user(user: Annotated[sqlite3.Row, Depends(current_user)]) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user

