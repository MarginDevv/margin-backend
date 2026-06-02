"""Order and OrderItem — facts table for analytics."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.menu_item import MenuItem
    from app.models.restaurant import Restaurant


class OrderStatus(str, enum.Enum):
    NEW = "new"
    CLOSED = "closed"
    CANCELED = "canceled"
    DELETED = "deleted"


class Order(TimestampedBase, RestaurantMixin):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "iiko_order_id", name="uq_order_iiko"),
    )

    iiko_order_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    iiko_order_number: Mapped[str | None] = mapped_column(String(32))

    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[OrderStatus] = mapped_column(
        SqlEnum(OrderStatus, name="order_status", values_callable=lambda e: [m.value for m in e]),
        default=OrderStatus.NEW,
        nullable=False,
    )

    guests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    waiter_name: Mapped[str | None] = mapped_column(String(128))

    # Aggregated totals (computed at sync time for speed).
    gross_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    net_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    total_food_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    profit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)

    restaurant: Mapped["Restaurant"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class OrderItem(TimestampedBase):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("menu_items.id", ondelete="SET NULL"),
        index=True,
    )
    iiko_product_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("1"), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    unit_food_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    line_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    line_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    line_profit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem | None"] = relationship(back_populates="order_items")
