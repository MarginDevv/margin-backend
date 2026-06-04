"""Referral program: codes per user, restaurants linked to a referrer,
accrued commissions tracked per payment period.

Payouts themselves (actual transfer of money) are out of scope of the v1 MVP —
they'll plug into the billing module later. For now we keep an append-only log
`referral_payouts` so we know who is owed how much.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class PayoutStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    REVERSED = "reversed"


class ReferralPayout(TimestampedBase, RestaurantMixin):
    """A single commission accrual line.

    Created whenever a restaurant's subscription invoice closes successfully.
    Aggregation per period is done at read time.
    """
    __tablename__ = "referral_payouts"

    referrer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source invoice / subscription period.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.10")
    )
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="RUB")

    status: Mapped[PayoutStatus] = mapped_column(
        SqlEnum(
            PayoutStatus,
            name="referral_payout_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=PayoutStatus.PENDING,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(String(512))

    referrer: Mapped[User] = relationship()
    restaurant: Mapped[Restaurant] = relationship()
