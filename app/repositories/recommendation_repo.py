"""Recommendation repository."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select

from app.models.recommendation import Recommendation, RecommendationStatus
from app.repositories.base import BaseRepository


class RecommendationRepository(BaseRepository[Recommendation]):
    model = Recommendation

    async def list_for_restaurant(
        self,
        restaurant_id: uuid.UUID,
        *,
        for_date: date | None = None,
        statuses: list[RecommendationStatus] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Recommendation]:
        stmt = select(Recommendation).where(Recommendation.restaurant_id == restaurant_id)
        if for_date:
            stmt = stmt.where(Recommendation.for_date == for_date)
        if statuses:
            stmt = stmt.where(Recommendation.status.in_(statuses))
        stmt = stmt.order_by(Recommendation.priority.desc(), Recommendation.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())

    async def delete_for_date(self, restaurant_id: uuid.UUID, for_date: date) -> int:
        from sqlalchemy import delete as sql_delete
        result = await self.session.execute(
            sql_delete(Recommendation).where(
                Recommendation.restaurant_id == restaurant_id,
                Recommendation.for_date == for_date,
                Recommendation.status == RecommendationStatus.NEW,
            )
        )
        return result.rowcount or 0
