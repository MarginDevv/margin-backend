"""Cached daily / weekly reports for fast dashboard reads."""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Integer, Numeric, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedBase
from app.models.mixins import RestaurantMixin

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class ReportPeriod(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class Report(TimestampedBase, RestaurantMixin):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint(
            "restaurant_id",
            "period",
            "period_start",
            name="uq_report_restaurant_period",
        ),
    )

    period: Mapped[ReportPeriod] = mapped_column(
        SqlEnum(ReportPeriod, name="report_period", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guests_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gross_revenue: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        nullable=False,
    )
    net_revenue: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        nullable=False,
    )
    total_food_cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        nullable=False,
    )
    profit: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        nullable=False,
    )
    avg_check: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
        nullable=False,
    )
    margin_percent: Mapped[Decimal] = mapped_column(
        Numeric(7, 4),
        default=Decimal("0"),
        nullable=False,
    )

    # Free-form breakdowns (top dishes, by-hour, by-day-of-week, etc.).
    breakdown: Mapped[dict | None] = mapped_column(JSONB)

    restaurant: Mapped[Restaurant] = relationship(back_populates="reports")
