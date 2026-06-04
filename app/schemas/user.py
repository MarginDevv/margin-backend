"""User schemas."""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel, TimestampedSchema


class UserRead(TimestampedSchema):
    email: EmailStr
    full_name: str | None
    phone: str | None
    is_active: bool
    is_superuser: bool


class UserUpdate(ORMModel):
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)


class PasswordChange(ORMModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
