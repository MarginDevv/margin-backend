"""Write activity events. Intentionally tiny — readers go through the repo."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_event import ActivityEvent, ActivityKind, ActivitySeverity


class ActivityEventService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def emit(
        self,
        restaurant_id: uuid.UUID,
        kind: ActivityKind,
        title: str,
        *,
        actor_user_id: uuid.UUID | None = None,
        severity: ActivitySeverity = ActivitySeverity.INFO,
        payload: dict[str, Any] | None = None,
    ) -> ActivityEvent:
        event = ActivityEvent(
            restaurant_id=restaurant_id,
            actor_user_id=actor_user_id,
            kind=kind,
            severity=severity,
            title=title,
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        return event
