"""Celery tasks for report generation."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from celery import chain

from app.core.logging import get_logger
from app.repositories.integration_repo import IikoIntegrationRepository
from app.services.analytics.report_service import ReportService
from app.services.analytics.schedule_service import due_business_day
from app.services.iiko.sync_service import IikoSyncService
from app.tasks._runner import run_async, with_session
from app.tasks.celery_app import celery_app
from app.utils.datetime import day_bounds_local, restaurant_tz

logger = get_logger("tasks.reports")

SCHEDULER_STEP_MINUTES = 15


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


@celery_app.task(
    name="app.tasks.reports.sync_day_then_build_daily",
    bind=True,
    max_retries=3,
)
def sync_day_then_build_daily(self, restaurant_id: str, for_date_iso: str) -> str:
    """Sync iiko orders for the given local day, then rebuild the daily report.

    This is the path used by both the per-restaurant scheduler and the on-demand
    endpoint — it guarantees the report reflects the latest closed cheques.
    """
    rid = uuid.UUID(restaurant_id)
    day = date.fromisoformat(for_date_iso)

    async def _sync(session):
        # Pin the bounds in the restaurant's TZ for correctness across DST.
        from app.repositories.restaurant_repo import RestaurantRepository

        restaurant = await RestaurantRepository(session).get(rid)
        if not restaurant:
            raise RuntimeError(f"Restaurant {rid} not found")
        tz = restaurant_tz(restaurant.timezone)
        # Sync a slightly wider window to capture late-arriving items that
        # were opened on the business day but closed shortly after.
        start_utc, end_utc = day_bounds_local(day, tz)
        end_utc = end_utc + timedelta(hours=4)
        return await IikoSyncService(session).sync_orders(rid, start_utc, end_utc)

    async def _build(session):
        return await ReportService(session).build_daily(rid, day)

    try:
        synced = run_async(with_session(_sync))
        report_id = run_async(with_session(_build))
        logger.info(
            "reports.daily.synced_and_built",
            restaurant_id=restaurant_id,
            day=day.isoformat(),
            synced=synced,
        )
        return str(report_id)
    except Exception as exc:
        logger.error(
            "reports.daily.sync_then_build.failed",
            restaurant_id=restaurant_id,
            day=day.isoformat(),
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="app.tasks.reports.build_daily_reports_all")
def build_daily_reports_all() -> int:
    """Safety-net fan-out — covers restaurants without configured hours."""

    async def _job(session):
        return await IikoIntegrationRepository(session).list_active_with_restaurant()

    integrations = run_async(with_session(_job))
    queued = 0
    for integration in integrations:
        if integration.restaurant.working_hours:
            continue  # handled by the per-restaurant scheduler
        build_daily_report.delay(str(integration.restaurant_id))
        queued += 1
    logger.info("reports.daily.fallback.fanout", queued=queued)
    return queued


@celery_app.task(name="app.tasks.reports.build_weekly_reports_all")
def build_weekly_reports_all() -> int:
    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    for integration in integrations:
        build_weekly_report.delay(str(integration.restaurant_id))
    return len(integrations)


@celery_app.task(name="app.tasks.reports.schedule_due_daily_reports")
def schedule_due_daily_reports() -> int:
    """Per-restaurant scheduler: fire ~1h (configurable) after closing.

    Runs every SCHEDULER_STEP_MINUTES minutes via Celery beat. For every active
    integration whose restaurant has working_hours configured, computes the
    most recent "close + delay" in the restaurant's local timezone. If that
    moment falls within the last step, queues `sync_day_then_build_daily`.
    """

    async def _job(session):
        return await IikoIntegrationRepository(session).list_active_with_restaurant()

    integrations = run_async(with_session(_job))
    queued = 0
    for integration in integrations:
        restaurant = integration.restaurant
        if not restaurant.working_hours:
            continue
        try:
            tz = ZoneInfo(restaurant.timezone or "Europe/Moscow")
        except Exception:
            logger.warning("reports.schedule.bad_tz", restaurant_id=str(restaurant.id))
            continue
        now_local = datetime.now(tz).replace(tzinfo=None)
        target = due_business_day(
            now_local,
            restaurant.working_hours,
            delay_minutes=restaurant.report_delay_minutes,
            step_minutes=SCHEDULER_STEP_MINUTES,
        )
        if not target:
            continue
        sync_day_then_build_daily.delay(str(restaurant.id), target.isoformat())
        queued += 1
        logger.info(
            "reports.schedule.queued",
            restaurant_id=str(restaurant.id),
            business_day=target.isoformat(),
        )
    return queued


def build_daily_on_demand(restaurant_id: uuid.UUID, for_date: date) -> str:
    """Queue an on-demand daily report build (sync + build). Returns the task id."""
    task = sync_day_then_build_daily.apply_async(
        args=[str(restaurant_id), for_date.isoformat()]
    )
    return task.id


def build_weekly_on_demand(restaurant_id: uuid.UUID, week_start: date) -> str:
    """Queue an on-demand weekly report build. Returns the task id.

    Chains: full sync of the week → weekly aggregate.
    """
    from app.tasks.iiko_sync import full_sync_restaurant

    task = chain(
        full_sync_restaurant.si(str(restaurant_id)),
        build_weekly_report.si(str(restaurant_id), week_start.isoformat()),
    ).apply_async()
    return task.id
