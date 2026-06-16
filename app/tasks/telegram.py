"""Celery tasks for outbound Telegram delivery."""
from __future__ import annotations

import uuid
from datetime import date

from app.core.logging import get_logger
from app.services.telegram.notifier import TelegramNotifier
from app.tasks._runner import run_async, with_session
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.telegram")


@celery_app.task(
    name="app.tasks.telegram.deliver_daily_digest",
    bind=True,
    max_retries=3,
)
def deliver_daily_digest(self, restaurant_id: str, for_date_iso: str) -> dict:
    """Idempotent: re-runs are safe — UNIQUE on telegram_deliveries blocks dupes."""
    rid = uuid.UUID(restaurant_id)
    day = date.fromisoformat(for_date_iso)

    async def _job(session):
        notifier = TelegramNotifier(session)
        return await notifier.deliver_daily_digest(rid, day)

    try:
        stats = run_async(with_session(_job))
        logger.info(
            "telegram.digest.delivered",
            restaurant_id=restaurant_id,
            for_date=for_date_iso,
            sent=stats.sent,
            queued=stats.queued,
            skipped_already_sent=stats.skipped_already_sent,
            failed=stats.failed,
        )
        return {
            "queued": stats.queued,
            "sent": stats.sent,
            "skipped_already_sent": stats.skipped_already_sent,
            "skipped_no_chat": stats.skipped_no_chat,
            "skipped_disabled": stats.skipped_disabled,
            "failed": stats.failed,
        }
    except Exception as exc:
        logger.error(
            "telegram.digest.failed",
            restaurant_id=restaurant_id,
            for_date=for_date_iso,
            error=str(exc),
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc
