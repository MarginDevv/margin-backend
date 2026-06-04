"""Analytics endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_member
from app.models.restaurant import Restaurant
from app.schemas.analytics import (
    DayPoint,
    DishesTopBottom,
    HourPoint,
    KpiSummary,
    WeekdayPoint,
)
from app.services.analytics.analytics_service import AnalyticsService

router = APIRouter()


def _default_range(start: date | None, end: date | None) -> tuple[date, date]:
    today = date.today()
    if not end:
        end = today
    if not start:
        start = end - timedelta(days=29)
    if start > end:
        raise ValueError("start must be <= end")
    return start, end


@router.get("/kpi", response_model=KpiSummary)
async def kpi(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> KpiSummary:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).kpi(restaurant, s, e)


@router.get("/by-hour", response_model=list[HourPoint])
async def by_hour(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[HourPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_hour(restaurant, s, e)


@router.get("/by-day", response_model=list[DayPoint])
async def by_day(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[DayPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_day(restaurant, s, e)


@router.get("/by-weekday", response_model=list[WeekdayPoint])
async def by_weekday(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
) -> list[WeekdayPoint]:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).by_weekday(restaurant, s, e)


@router.get("/dishes", response_model=DishesTopBottom)
async def dishes(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    top_n: int = Query(default=10, ge=1, le=100),
) -> DishesTopBottom:
    s, e = _default_range(start, end)
    return await AnalyticsService(session).dishes_top_bottom(restaurant, s, e, top_n=top_n)
