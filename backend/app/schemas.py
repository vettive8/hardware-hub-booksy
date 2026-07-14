from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

HardwareStatus = Literal["Available", "In Use", "Repair"]
HardwareCategory = Literal["Laptop", "Mobile", "Tablet", "Monitor", "Accessory"]


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
    serial_number: str | None = Field(default=None, min_length=2, max_length=80)
    category: HardwareCategory | None = None
    purchase_date: str | None = None
    status: HardwareStatus = "Available"
    notes: str | None = None


class RepairUpdate(BaseModel):
    resolve_damage: bool = False
    resolution_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_resolution_note(self):
        if self.resolve_damage and (not self.resolution_note or len(self.resolution_note.strip()) < 5):
            raise ValueError("A repair resolution note of at least 5 characters is required")
        return self


class HardwareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str
    serial_number: str | None
    category: HardwareCategory | None
    purchase_date: str | None
    status: HardwareStatus
    notes: str | None
    history: str | None
    assigned_to: str | None
    is_damaged: bool
