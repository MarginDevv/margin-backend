"""Reports endpoints — read cached reports and trigger on-demand rebuilds."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel

from app.core.dependencies import DbSession, require_manager, require_member
from app.core.exceptions import NotFoundError, ValidationError
from app.models.report import ReportPeriod
from app.models.restaurant import Restaurant
from app.repositories.report_repo import ReportRepository
from app.schemas.report import ReportRead
from app.utils.datetime import now_utc

router = APIRouter()


class BuildResponse(BaseModel):
    task_id: str
    restaurant_id: str
    period: ReportPeriod
    period_start: date
    queued_at: datetime


@router.get("/daily", response_model=ReportRead)
async def get_daily(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    for_date: date = Query(...),
) -> ReportRead:
    report = await ReportRepository(session).get_for_period(restaurant.id, ReportPeriod.DAILY, for_date)
    if not report:
        raise NotFoundError("Daily report not found for this date")
    return ReportRead.model_validate(report)


@router.get("/weekly", response_model=ReportRead)
async def get_weekly(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    week_start: date = Query(..., description="Monday of the target ISO week"),
) -> ReportRead:
    report = await ReportRepository(session).get_for_period(restaurant.id, ReportPeriod.WEEKLY, week_start)
    if not report:
        raise NotFoundError("Weekly report not found for this week")
    return ReportRead.model_validate(report)


@router.post(
    "/daily/build",
    response_model=BuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger sync + daily report rebuild on demand",
)
async def build_daily(
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    for_date: date = Query(
        default=None,
        description="Business day to build. Defaults to yesterday in restaurant TZ.",
    ),
) -> BuildResponse:
    from app.tasks.reports import build_daily_on_demand

    target = for_date or (date.today() - timedelta(days=1))
    if target > date.today():
        raise ValidationError("Cannot build a report for a future date")
    task_id = build_daily_on_demand(restaurant.id, target)
    return BuildResponse(
        task_id=task_id,
        restaurant_id=str(restaurant.id),
        period=ReportPeriod.DAILY,
        period_start=target,
        queued_at=now_utc(),
    )


@router.post(
    "/daily/deliver",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually push the daily digest to Telegram subscribers",
)
async def deliver_daily(
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    for_date: date = Query(default=None),
) -> dict:
    from app.tasks.telegram import deliver_daily_digest

    target = for_date or (date.today() - timedelta(days=1))
    if target > date.today():
        raise ValidationError("Cannot deliver a digest for a future date")
    task = deliver_daily_digest.delay(str(restaurant.id), target.isoformat())
    return {
        "task_id": task.id,
        "restaurant_id": str(restaurant.id),
        "for_date": target.isoformat(),
        "queued_at": now_utc().isoformat(),
    }


@router.post(
    "/weekly/build",
    response_model=BuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger sync + weekly report rebuild on demand",
)
async def build_weekly(
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    week_start: date = Query(
        default=None,
        description="Monday of the target ISO week. Defaults to previous Monday.",
    ),
) -> BuildResponse:
    from app.tasks.reports import build_weekly_on_demand

    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday() + 7)
    if week_start.weekday() != 0:
        raise ValidationError("week_start must be a Monday")
    if week_start > date.today():
        raise ValidationError("Cannot build a report for a future week")
    task_id = build_weekly_on_demand(restaurant.id, week_start)
    return BuildResponse(
        task_id=task_id,
        restaurant_id=str(restaurant.id),
        period=ReportPeriod.WEEKLY,
        period_start=week_start,
        queued_at=now_utc(),
    )
