"""Recommendation endpoints."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_manager, require_member
from app.core.exceptions import NotFoundError
from app.models.recommendation import RecommendationStatus
from app.models.restaurant import Restaurant
from app.repositories.recommendation_repo import RecommendationRepository
from app.schemas.recommendation import RecommendationRead, RecommendationStatusUpdate

router = APIRouter()


@router.get("", response_model=list[RecommendationRead])
async def list_recommendations(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    for_date: date | None = Query(default=None),
    status: list[RecommendationStatus] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[RecommendationRead]:
    rows = await RecommendationRepository(session).list_for_restaurant(
        restaurant.id, for_date=for_date, statuses=status, limit=limit, offset=offset
    )
    return [RecommendationRead.model_validate(r) for r in rows]


@router.patch("/{recommendation_id}", response_model=RecommendationRead)
async def update_status(
    recommendation_id: uuid.UUID,
    payload: RecommendationStatusUpdate,
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    session: DbSession,
) -> RecommendationRead:
    repo = RecommendationRepository(session)
    rec = await repo.get(recommendation_id)
    if not rec or rec.restaurant_id != restaurant.id:
        raise NotFoundError("Recommendation not found")
    rec.status = payload.status
    await session.commit()
    await session.refresh(rec)
    return RecommendationRead.model_validate(rec)
