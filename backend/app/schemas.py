from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

HardwareStatus = Literal["Available", "In Use", "Repair"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "user"] = "user"


class HardwareCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    brand: str = Field(min_length=1, max_length=80)
    purchase_date: str | None = None
    status: HardwareStatus = "Available"
    notes: str | None = None


class HardwareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str
    purchase_date: str | None
    status: HardwareStatus
    notes: str | None
    history: str | None
    assigned_to: str | None
    is_damaged: bool

