"""Auth-related Pydantic schemas."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    restaurant_name: str = Field(min_length=1, max_length=255)
    referral_code: str | None = Field(default=None, max_length=16)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserContext(BaseModel):
    user_id: uuid.UUID
    email: str
    is_superuser: bool = False
