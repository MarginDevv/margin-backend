"""Subscription model bound to a restaurant."""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

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


class Subscription(TimestampedBase, RestaurantMixin):
    __tablename__ = "subscriptions"
    __restaurant_unique__ = True

    plan: Mapped[SubscriptionPlan] = mapped_column(
        SqlEnum(SubscriptionPlan, name="subscription_plan", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SubscriptionPlan.FREE_TRIAL,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        SqlEnum(SubscriptionStatus, name="subscription_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=SubscriptionStatus.TRIAL,
    )
    price: Mapped["Decimal | None"] = mapped_column(Numeric(12, 2))
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    restaurant: Mapped["Restaurant"] = relationship(back_populates="subscription")
