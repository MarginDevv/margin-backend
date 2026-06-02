"""Reports endpoints."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import DbSession, require_member
from app.core.exceptions import NotFoundError
from app.models.report import ReportPeriod
from app.models.restaurant import Restaurant
from app.repositories.report_repo import ReportRepository
from app.schemas.report import ReportRead

router = APIRouter()


@router.get("/daily", response_model=ReportRead)
async def get_daily(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    for_date: date = Query(...),
) -> ReportRead:
    report = await ReportRepository(session).get(restaurant.id, ReportPeriod.DAILY, for_date)
    if not report:
        raise NotFoundError("Daily report not found for this date")
    return ReportRead.model_validate(report)


@router.get("/weekly", response_model=ReportRead)
async def get_weekly(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    week_start: date = Query(..., description="Monday of the target ISO week"),
) -> ReportRead:
    report = await ReportRepository(session).get(restaurant.id, ReportPeriod.WEEKLY, week_start)
    if not report:
        raise NotFoundError("Weekly report not found for this week")
    return ReportRead.model_validate(report)
