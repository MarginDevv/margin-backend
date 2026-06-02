"""Restaurant schemas."""
from __future__ import annotations

import uuid

from pydantic import Field

from app.models.user_restaurant_role import Role
from app.schemas.common import ORMModel, TimestampedSchema


class RestaurantCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    timezone: str = "Europe/Moscow"
    currency: str = "RUB"


class RestaurantUpdate(ORMModel):
    name: str | None = Field(default=None, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = None
    currency: str | None = None
    is_active: bool | None = None


class RestaurantRead(TimestampedSchema):
    name: str
    legal_name: str | None
    timezone: str
    currency: str
    is_active: bool


class MemberInvite(ORMModel):
    user_email: str
    role: Role


class MemberRead(TimestampedSchema):
    user_id: uuid.UUID
    restaurant_id: uuid.UUID
    role: Role
