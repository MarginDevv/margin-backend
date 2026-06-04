"""Analytics queries on top of OrderRepository, returning Pydantic models."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.restaurant import Restaurant
from app.repositories.order_repo import OrderRepository
from app.schemas.analytics import (
    DayPoint,
    DishesTopBottom,
    DishPerformance,
    HourPoint,
    KpiSummary,
    WeekdayPoint,
)


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)

    @staticmethod
    def _bounds(restaurant: Restaurant, start: date, end: date) -> tuple[datetime, datetime, str]:
        tz_name = restaurant.timezone or "Europe/Moscow"
        tz = ZoneInfo(tz_name)
        start_local = datetime.combine(start, time.min, tzinfo=tz)
        end_local = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
        return start_local, end_local, tz_name

    async def kpi(self, restaurant: Restaurant, start: date, end: date) -> KpiSummary:
        start_utc, end_utc, _ = self._bounds(restaurant, start, end)
        row = await self.orders.kpi_summary(restaurant.id, start_utc, end_utc)
        orders_count = int(row["orders_count"])
        net_revenue = Decimal(str(row["net_revenue"]))
        profit = Decimal(str(row["profit"]))
        avg_check = (net_revenue / orders_count) if orders_count else Decimal("0")
        margin_pct = (profit / net_revenue * Decimal("100")) if net_revenue else Decimal("0")
        return KpiSummary(
            period_start=start,
            period_end=end,
            orders_count=orders_count,
            guests_count=int(row["guests_count"]),
            gross_revenue=Decimal(str(row["gross_revenue"])),
            net_revenue=net_revenue,
            total_food_cost=Decimal(str(row["total_food_cost"])),
            profit=profit,
            avg_check=avg_check,
            margin_percent=margin_pct,
        )

    async def by_hour(self, restaurant: Restaurant, start: date, end: date) -> list[HourPoint]:
        s, e, tz = self._bounds(restaurant, start, end)
        rows = await self.orders.by_hour(restaurant.id, s, e, tz)
        return [
            HourPoint(
                hour=int(r["hour"]),
                orders_count=int(r["orders_count"]),
                revenue=Decimal(str(r["revenue"])),
                profit=Decimal(str(r["profit"])),
            )
            for r in rows
        ]

    async def by_day(self, restaurant: Restaurant, start: date, end: date) -> list[DayPoint]:
        s, e, tz = self._bounds(restaurant, start, end)
        rows = await self.orders.by_day(restaurant.id, s, e, tz)
        return [
            DayPoint(
                day=r["day"],
                orders_count=int(r["orders_count"]),
                revenue=Decimal(str(r["revenue"])),
                profit=Decimal(str(r["profit"])),
            )
            for r in rows
        ]

    async def by_weekday(
        self, restaurant: Restaurant, start: date, end: date
    ) -> list[WeekdayPoint]:
        s, e, tz = self._bounds(restaurant, start, end)
        rows = await self.orders.by_weekday(restaurant.id, s, e, tz)
        return [
            WeekdayPoint(
                weekday=int(r["weekday"]),
                orders_count=int(r["orders_count"]),
                revenue=Decimal(str(r["revenue"])),
                profit=Decimal(str(r["profit"])),
            )
            for r in rows
        ]

    async def dishes_top_bottom(
        self, restaurant: Restaurant, start: date, end: date, *, top_n: int = 10
    ) -> DishesTopBottom:
        s, e, _ = self._bounds(restaurant, start, end)
        rows = await self.orders.dish_performance(restaurant.id, s, e, limit=500)
        perfs = [
            DishPerformance(
                menu_item_id=r["menu_item_id"],
                name=r["name"],
                category=r.get("category"),
                quantity=Decimal(str(r["quantity"])),
                revenue=Decimal(str(r["revenue"])),
                cost=Decimal(str(r["cost"])),
                profit=Decimal(str(r["profit"])),
                margin_percent=Decimal(str(r["margin_percent"])),
            )
            for r in rows
        ]
        top = sorted(perfs, key=lambda x: x.profit, reverse=True)[:top_n]
        bottom = sorted(perfs, key=lambda x: x.profit)[:top_n]
        return DishesTopBottom(top=top, bottom=bottom)

    async def best_worst_weekday(
        self, restaurant: Restaurant, start: date, end: date
    ) -> tuple[WeekdayPoint | None, WeekdayPoint | None]:
        """Best/worst weekday by profit — used in recommendations."""
        points = await self.by_weekday(restaurant, start, end)
        if not points:
            return None, None
        best = max(points, key=lambda p: p.profit)
        worst = min(points, key=lambda p: p.profit)
        return best, worst
