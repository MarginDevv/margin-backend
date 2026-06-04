"""Activity feed schemas."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.activity_event import ActivityKind, ActivitySeverity
from app.schemas.common import TimestampedSchema


class ActivityEventRead(TimestampedSchema):
    restaurant_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    kind: ActivityKind
    severity: ActivitySeverity
    title: str
    payload: dict[str, Any] | None
