"""Report schemas."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.models.report import ReportPeriod
from app.schemas.common import TimestampedSchema


class ReportRead(TimestampedSchema):
    period: ReportPeriod
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
    breakdown: dict[str, Any] | None
