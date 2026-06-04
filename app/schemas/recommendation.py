"""Recommendation schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.models.recommendation import (
    RecommendationPriority,
    RecommendationStatus,
    RecommendationType,
)
from app.schemas.common import ORMModel, TimestampedSchema


class RecommendationRead(TimestampedSchema):
    for_date: date
    type: RecommendationType
    priority: RecommendationPriority
    status: RecommendationStatus
    title: str
    description: str
    action: str | None
    estimated_uplift: Decimal | None
    confidence: int
    payload: dict[str, Any] | None


class RecommendationStatusUpdate(ORMModel):
    status: RecommendationStatus
