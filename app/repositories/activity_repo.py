"""Activity-event repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.activity_event import ActivityEvent, ActivityKind, ActivitySeverity
from app.repositories.base import BaseRepository


class ActivityEventRepository(BaseRepository[ActivityEvent]):
    model = ActivityEvent

    async def list_for_restaurant(
        self,
        restaurant_id: uuid.UUID,
        *,
        kinds: list[ActivityKind] | None = None,
        severity_at_least: ActivitySeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityEvent]:
        stmt = select(ActivityEvent).where(ActivityEvent.restaurant_id == restaurant_id)
        if kinds:
            stmt = stmt.where(ActivityEvent.kind.in_(kinds))
        if severity_at_least:
            order = {
                ActivitySeverity.INFO: 0,
                ActivitySeverity.WARNING: 1,
                ActivitySeverity.ERROR: 2,
            }
            min_rank = order[severity_at_least]
            allowed = [s for s, r in order.items() if r >= min_rank]
            stmt = stmt.where(ActivityEvent.severity.in_(allowed))
        stmt = stmt.order_by(ActivityEvent.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.scalars(stmt)).all())
