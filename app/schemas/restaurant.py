"""Restaurant schemas."""
from __future__ import annotations

import re
import uuid
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.models.user_restaurant_role import Role
from app.schemas.common import ORMModel, TimestampedSchema

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class WorkingHoursDay(BaseModel):
    """Open / close times in HH:MM. close < open ⇒ spans midnight."""
    open: str = Field(description="HH:MM, restaurant-local time")
    close: str = Field(description="HH:MM, restaurant-local time")

    @field_validator("open", "close")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        if not _TIME_RE.fullmatch(value):
            raise ValueError("Expected time in HH:MM, 24h format")
        return value


WorkingHours = Annotated[
    dict[str, WorkingHoursDay | None],
    Field(
        description=(
            "Working hours keyed by weekday: mon/tue/wed/thu/fri/sat/sun. "
            "Missing or null weekday means closed all day."
        )
    ),
]


def _validate_working_hours(value: dict | None) -> dict | None:
    if value is None:
        return None
    unknown = set(value) - set(WEEKDAYS)
    if unknown:
        raise ValueError(f"Unknown weekday keys: {sorted(unknown)}; expected {WEEKDAYS}")
    return value


class RestaurantCreate(ORMModel):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    timezone: str = "Europe/Moscow"
    currency: str = "RUB"
    working_hours: WorkingHours | None = None
    report_delay_minutes: int = Field(default=60, ge=0, le=720)
    referral_code: str | None = Field(default=None, max_length=16)

    @field_validator("working_hours")
    @classmethod
    def _v_hours(cls, value):
        return _validate_working_hours(value)


class RestaurantUpdate(ORMModel):
    name: str | None = Field(default=None, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    timezone: str | None = None
    currency: str | None = None
    is_active: bool | None = None
    working_hours: WorkingHours | None = None
    report_delay_minutes: int | None = Field(default=None, ge=0, le=720)

    @field_validator("working_hours")
    @classmethod
    def _v_hours(cls, value):
        return _validate_working_hours(value)


class RestaurantRead(TimestampedSchema):
    name: str
    legal_name: str | None
    timezone: str
    currency: str
    is_active: bool
    working_hours: dict | None
    report_delay_minutes: int


class MemberInvite(ORMModel):
    user_email: str
    role: Role


class MemberRead(TimestampedSchema):
    user_id: uuid.UUID
    restaurant_id: uuid.UUID
    role: Role
