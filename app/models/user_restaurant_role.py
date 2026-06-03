"""Join table for users <-> restaurants with role."""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin, UserMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant
    from app.models.user import User


class Role(str, enum.Enum):
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"


class UserRestaurantRole(TimestampedBase, RestaurantMixin, UserMixin):
    __tablename__ = "user_restaurant_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "restaurant_id", name="uq_user_restaurant"),
    )

    role: Mapped[Role] = mapped_column(
        SqlEnum(Role, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    telegram_notifications: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="roles", lazy="joined")
    restaurant: Mapped["Restaurant"] = relationship(back_populates="roles", lazy="joined")
