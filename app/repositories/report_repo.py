"""Report repository."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.report import Report, ReportPeriod
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[Report]):
    model = Report

    async def get_for_period(
        self, restaurant_id: uuid.UUID, period: ReportPeriod, period_start: date
    ) -> Report | None:
        stmt = select(Report).where(
            Report.restaurant_id == restaurant_id,
            Report.period == period,
            Report.period_start == period_start,
        )
        return await self.session.scalar(stmt)

    async def upsert(self, row: dict) -> uuid.UUID:
        stmt = insert(Report).values(row).on_conflict_do_update(
            constraint="uq_report_restaurant_period",
            set_={
                "period_end": row["period_end"],
                "orders_count": row["orders_count"],
                "guests_count": row["guests_count"],
                "gross_revenue": row["gross_revenue"],
                "net_revenue": row["net_revenue"],
                "total_food_cost": row["total_food_cost"],
                "profit": row["profit"],
                "avg_check": row["avg_check"],
                "margin_percent": row["margin_percent"],
                "breakdown": row.get("breakdown"),
            },
        ).returning(Report.id)
        return (await self.session.execute(stmt)).scalar_one()
