"""Writeoff documents synced from iiko — basis for inventory-leak detection."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.menu_item import MenuItem
    from app.models.restaurant import Restaurant


class Writeoff(TimestampedBase):
    __tablename__ = "writeoffs"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "iiko_document_id", name="uq_writeoff_iiko"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iiko_document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    iiko_document_number: Mapped[str | None] = mapped_column(String(32))

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    store_name: Mapped[str | None] = mapped_column(String(255))
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(String(1024))

    restaurant: Mapped["Restaurant"] = relationship()
    items: Mapped[list["WriteoffItem"]] = relationship(
        back_populates="writeoff",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WriteoffItem(TimestampedBase):
    __tablename__ = "writeoff_items"

    writeoff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("writeoffs.id", ondelete="CASCADE"),
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

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), default=Decimal("0"), nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    line_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(255))

    writeoff: Mapped["Writeoff"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem | None"] = relationship()
