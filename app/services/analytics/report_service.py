"""Build and persist daily/weekly reports."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.report import ReportPeriod
from app.repositories.report_repo import ReportRepository
from app.repositories.restaurant_repo import RestaurantRepository
from app.services.analytics.analytics_service import AnalyticsService


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportRepository(session)

    async def build_daily(self, restaurant_id: uuid.UUID, day: date) -> uuid.UUID:
        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")
        analytics = AnalyticsService(self.session)
        kpi = await analytics.kpi(restaurant, day, day)
        hours = await analytics.by_hour(restaurant, day, day)
        dishes = await analytics.dishes_top_bottom(restaurant, day, day, top_n=10)

        breakdown = {
            "by_hour": [p.model_dump(mode="json") for p in hours],
            "top_dishes": [d.model_dump(mode="json") for d in dishes.top],
            "bottom_dishes": [d.model_dump(mode="json") for d in dishes.bottom],
        }
        row = self._report_row(restaurant_id, ReportPeriod.DAILY, day, day, kpi, breakdown)
        report_id = await self.reports.upsert(row)
        await self.session.commit()
        return report_id

    async def build_weekly(self, restaurant_id: uuid.UUID, week_start: date) -> uuid.UUID:
        if week_start.weekday() != 0:
            week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6)

        restaurant = await RestaurantRepository(self.session).get(restaurant_id)
        if not restaurant:
            raise NotFoundError("Restaurant not found")
        analytics = AnalyticsService(self.session)
        kpi = await analytics.kpi(restaurant, week_start, week_end)
        days = await analytics.by_day(restaurant, week_start, week_end)
        weekdays = await analytics.by_weekday(restaurant, week_start, week_end)
        dishes = await analytics.dishes_top_bottom(restaurant, week_start, week_end, top_n=10)
        best, worst = await analytics.best_worst_weekday(restaurant, week_start, week_end)

        breakdown = {
            "by_day": [p.model_dump(mode="json") for p in days],
            "by_weekday": [p.model_dump(mode="json") for p in weekdays],
            "top_dishes": [d.model_dump(mode="json") for d in dishes.top],
            "bottom_dishes": [d.model_dump(mode="json") for d in dishes.bottom],
            "best_weekday_by_profit": best.model_dump(mode="json") if best else None,
            "worst_weekday_by_profit": worst.model_dump(mode="json") if worst else None,
        }
        row = self._report_row(
            restaurant_id, ReportPeriod.WEEKLY, week_start, week_end, kpi, breakdown
        )
        report_id = await self.reports.upsert(row)
        await self.session.commit()
        return report_id

    @staticmethod
    def _report_row(
        restaurant_id: uuid.UUID,
        period: ReportPeriod,
        period_start: date,
        period_end: date,
        kpi,
        breakdown: dict,
    ) -> dict:
        return {
            "restaurant_id": restaurant_id,
            "period": period,
            "period_start": period_start,
            "period_end": period_end,
            "orders_count": kpi.orders_count,
            "guests_count": kpi.guests_count,
            "gross_revenue": kpi.gross_revenue,
            "net_revenue": kpi.net_revenue,
            "total_food_cost": kpi.total_food_cost,
            "profit": kpi.profit,
            "avg_check": kpi.avg_check,
            "margin_percent": kpi.margin_percent if kpi.margin_percent else Decimal("0"),
            "breakdown": breakdown,
        }
