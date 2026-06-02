"""Celery tasks for report generation."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core.logging import get_logger
from app.repositories.integration_repo import IikoIntegrationRepository
from app.services.analytics.report_service import ReportService
from app.tasks._runner import run_async, with_session
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.reports")


@celery_app.task(name="app.tasks.reports.build_daily_report")
def build_daily_report(restaurant_id: str, for_date_iso: str | None = None) -> str:
    rid = uuid.UUID(restaurant_id)
    day = date.fromisoformat(for_date_iso) if for_date_iso else (date.today() - timedelta(days=1))

    async def _job(session):
        return await ReportService(session).build_daily(rid, day)

    report_id = run_async(with_session(_job))
    logger.info("reports.daily.built", restaurant_id=restaurant_id, day=day.isoformat())
    return str(report_id)


@celery_app.task(name="app.tasks.reports.build_weekly_report")
def build_weekly_report(restaurant_id: str, week_start_iso: str | None = None) -> str:
    rid = uuid.UUID(restaurant_id)
    if week_start_iso:
        start = date.fromisoformat(week_start_iso)
    else:
        today = date.today()
        start = today - timedelta(days=today.weekday() + 7)  # previous ISO week Monday

    async def _job(session):
        return await ReportService(session).build_weekly(rid, start)

    report_id = run_async(with_session(_job))
    logger.info("reports.weekly.built", restaurant_id=restaurant_id, week_start=start.isoformat())
    return str(report_id)


@celery_app.task(name="app.tasks.reports.build_daily_reports_all")
def build_daily_reports_all() -> int:
    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    for integration in integrations:
        build_daily_report.delay(str(integration.restaurant_id))
    return len(integrations)


@celery_app.task(name="app.tasks.reports.build_weekly_reports_all")
def build_weekly_reports_all() -> int:
    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    for integration in integrations:
        build_weekly_report.delay(str(integration.restaurant_id))
    return len(integrations)
