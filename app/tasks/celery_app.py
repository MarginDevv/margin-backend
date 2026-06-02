"""Celery application + beat schedule."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "margin",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=[
        "app.tasks.iiko_sync",
        "app.tasks.reports",
        "app.tasks.recommendations",
        "app.tasks.telegram",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.app_timezone,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    # Incremental sync every 15 minutes for all active integrations.
    "iiko-incremental-sync-all": {
        "task": "app.tasks.iiko_sync.incremental_sync_all",
        "schedule": crontab(minute="*/15"),
    },
    # Full re-sync of yesterday's orders at 04:00 local time + nomenclature refresh.
    "iiko-daily-full-sync": {
        "task": "app.tasks.iiko_sync.daily_full_sync_all",
        "schedule": crontab(hour=4, minute=0),
    },
    # Per-restaurant daily report ~1h after each restaurant's close.
    # Runs every 15 min; only fires for restaurants whose close+delay matches.
    "schedule-due-daily-reports": {
        "task": "app.tasks.reports.schedule_due_daily_reports",
        "schedule": crontab(minute="*/15"),
    },
    # Safety net for restaurants without working_hours configured.
    "build-daily-reports-fallback": {
        "task": "app.tasks.reports.build_daily_reports_all",
        "schedule": crontab(hour=5, minute=0),
    },
    # Weekly reports on Monday 05:30.
    "build-weekly-reports": {
        "task": "app.tasks.reports.build_weekly_reports_all",
        "schedule": crontab(day_of_week="mon", hour=5, minute=30),
    },
    # Generate daily recommendations at 06:00.
    "generate-daily-recommendations": {
        "task": "app.tasks.recommendations.generate_daily_all",
        "schedule": crontab(hour=6, minute=0),
    },
}
