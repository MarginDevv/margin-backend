"""Restaurant (tenant) model."""
from __future__ import annotations

from typing import TYPE_CHECKING

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.iiko_integration import IikoIntegration
    from app.models.menu_item import MenuItem
    from app.models.order import Order
    from app.models.recommendation import Recommendation
    from app.models.report import Report
    from app.models.subscription import Subscription
    from app.models.user_restaurant_role import UserRestaurantRole


class Restaurant(TimestampedBase):
    __tablename__ = "restaurants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Working hours: { "mon": {"open": "10:00", "close": "23:00"}, ... }
    # close < open means the business day spans midnight (e.g., 18:00-02:00).
    # A weekday absent or set to null means the restaurant is closed that day.
    working_hours: Mapped[dict | None] = mapped_column(JSONB)
    # Minutes after closing time to build the daily report.
    report_delay_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    # Referral: who brought this restaurant in. Set once at registration.
    referrer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )

    roles: Mapped[list["UserRestaurantRole"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="restaurant",
        uselist=False,
        cascade="all, delete-orphan",
    )
    iiko_integration: Mapped["IikoIntegration | None"] = relationship(
        back_populates="restaurant",
        uselist=False,
        cascade="all, delete-orphan",
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Restaurant {self.name}>"
