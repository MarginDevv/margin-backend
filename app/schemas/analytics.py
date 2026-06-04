"""Analytics / dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from app.schemas.common import ORMModel


class KpiSummary(ORMModel):
    """Top-level KPI for a date range."""

    period_start: date
    period_end: date
    orders_count: int
    guests_count: int
    gross_revenue: Decimal
    net_revenue: Decimal
    total_food_cost: Decimal
    profit: Decimal
    avg_check: Decimal
    margin_percent: Decimal


class HourPoint(ORMModel):
    hour: int  # 0..23 in restaurant local tz
    orders_count: int
    revenue: Decimal
    profit: Decimal


class DayPoint(ORMModel):
    day: date
    orders_count: int
    revenue: Decimal
    profit: Decimal


class WeekdayPoint(ORMModel):
    weekday: int  # 0=Mon .. 6=Sun
    orders_count: int
    revenue: Decimal
    profit: Decimal


class DishPerformance(ORMModel):
    menu_item_id: uuid.UUID | None
    name: str
    category: str | None
    quantity: Decimal
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal


class DishesTopBottom(ORMModel):
    top: list[DishPerformance]
    bottom: list[DishPerformance]
