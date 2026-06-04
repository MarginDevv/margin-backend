"""Referral program schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.models.referral import PayoutStatus
from app.schemas.common import TimestampedSchema


class ReferralProfile(BaseModel):
    code: str
    share_url: str
    referred_restaurants: int
    total_pending: Decimal
    total_paid: Decimal
    by_status: dict[str, Any]


class ReferralPayoutRead(TimestampedSchema):
    referrer_user_id: uuid.UUID
    restaurant_id: uuid.UUID
    period_start: date
    period_end: date
    invoice_amount: Decimal
    commission_rate: Decimal
    commission_amount: Decimal
    currency: str
    status: PayoutStatus
    paid_at: datetime | None
    notes: str | None
