"""Restaurant (tenant) model."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
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
