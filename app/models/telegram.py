"""Telegram link tokens (deep-link onboarding) and delivery records."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class TelegramLinkToken(TimestampedBase):
    __tablename__ = "telegram_link_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryKind(str, enum.Enum):
    DAILY_DIGEST = "daily_digest"
    WEEKLY_DIGEST = "weekly_digest"
    ALERT = "alert"
    SYSTEM = "system"


class TelegramDelivery(TimestampedBase):
    """Idempotency log for outbound notifications.

    Unique by (restaurant_id, user_id, kind, for_date) — re-runs of the digest
    pipeline never spam users twice.
    """
    __tablename__ = "telegram_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "restaurant_id", "user_id", "kind", "for_date",
            name="uq_telegram_delivery",
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[DeliveryKind] = mapped_column(
        SqlEnum(DeliveryKind, name="telegram_delivery_kind", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    for_date: Mapped[str | None] = mapped_column(String(10))  # ISO date or null for system
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(1024))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    restaurant: Mapped["Restaurant"] = relationship()
    user: Mapped["User"] = relationship()
