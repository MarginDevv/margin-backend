"""Activity-feed endpoint powering the dashboard's «recent changes» view."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_member
from app.models.activity_event import ActivityKind, ActivitySeverity
from app.models.restaurant import Restaurant
from app.repositories.activity_repo import ActivityEventRepository
from app.schemas.activity import ActivityEventRead

router = APIRouter()


@router.get("", response_model=list[ActivityEventRead])
async def list_activity(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    kind: list[ActivityKind] | None = Query(default=None),
    severity_at_least: ActivitySeverity | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ActivityEventRead]:
    events = await ActivityEventRepository(session).list_for_restaurant(
        restaurant.id,
        kinds=kind,
        severity_at_least=severity_at_least,
        limit=limit,
        offset=offset,
    )
    return [ActivityEventRead.model_validate(e) for e in events]
