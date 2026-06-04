"""Subscription model bound to a restaurant."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class SubscriptionPlan(str, enum.Enum):
    FREE_TRIAL = "free_trial"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"


class Subscription(TimestampedBase):
    __tablename__ = "subscriptions"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan: Mapped[SubscriptionPlan] = mapped_column(
        SqlEnum(
            SubscriptionPlan, name="subscription_plan",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SubscriptionPlan.FREE_TRIAL,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(
            SubscriptionStatus, name="subscription_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=SubscriptionStatus.TRIAL,
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    restaurant: Mapped[Restaurant] = relationship(back_populates="subscription")
