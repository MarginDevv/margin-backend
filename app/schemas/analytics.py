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


class DishDailyStat(ORMModel):
    """One row per (date, dish) — flat fact for the dashboard."""
    day: date
    menu_item_id: uuid.UUID | None
    name: str
    category: str | None
    quantity: Decimal
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal


class DishTrendPoint(ORMModel):
    bucket: date
    quantity: Decimal
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal


class DishTrend(ORMModel):
    menu_item_id: uuid.UUID
    name: str
    category: str | None
    granularity: str
    points: list[DishTrendPoint]


class CategoryPerformance(ORMModel):
    category: str
    dishes_count: int
    quantity: Decimal
    revenue: Decimal
    cost: Decimal
    profit: Decimal
    margin_percent: Decimal


class KpiComparison(ORMModel):
    """KPI for two equal-length consecutive periods + delta percentages.

    `current` and `previous` use the same metric set so the dashboard can
    render any of them with one component.
    """
    current: "KpiSummary"
    previous: "KpiSummary"
    # Deltas as percentages (current - previous) / previous * 100.
    # Null when previous == 0 (no baseline to compare against).
    delta_orders_count: Decimal | None
    delta_guests_count: Decimal | None
    delta_net_revenue: Decimal | None
    delta_profit: Decimal | None
    delta_avg_check: Decimal | None
    delta_margin_percent: Decimal | None


class HeatmapCell(ORMModel):
    """One cell of the weekday × hour heatmap."""
    weekday: int  # 0 = Mon … 6 = Sun
    hour: int  # 0..23 in restaurant local tz
    value: Decimal
    orders_count: int


class Heatmap(ORMModel):
    metric: str  # "revenue" | "profit" | "orders"
    period_start: date
    period_end: date
    cells: list[HeatmapCell]


class DishPair(ORMModel):
    """A pair of dishes that frequently appear in the same order."""
    item_a_id: uuid.UUID
    item_a_name: str
    item_a_category: str | None
    item_b_id: uuid.UUID
    item_b_name: str
    item_b_category: str | None
    orders_count: int
    combined_revenue: Decimal
    combined_profit: Decimal
