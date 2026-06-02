"""Celery tasks for recommendation generation."""
from __future__ import annotations

import uuid
from datetime import date

from app.core.logging import get_logger
from app.repositories.integration_repo import IikoIntegrationRepository
from app.services.recommendations.engine import RecommendationEngine
from app.tasks._runner import run_async, with_session
from app.tasks.celery_app import celery_app

logger = get_logger("tasks.recommendations")


@celery_app.task(name="app.tasks.recommendations.generate_daily")
def generate_daily(restaurant_id: str, for_date_iso: str | None = None) -> int:
    rid = uuid.UUID(restaurant_id)
    target = date.fromisoformat(for_date_iso) if for_date_iso else date.today()

    async def _job(session):
        return await RecommendationEngine(session).generate_for(rid, target)

    count = run_async(with_session(_job))
    logger.info("recs.generated", restaurant_id=restaurant_id, count=count, for_date=target.isoformat())

    # Once recs are ready, ask the notifier to push the digest. The digest task
    # is idempotent — safe to enqueue from multiple hooks for the same date.
    from app.tasks.telegram import deliver_daily_digest

    deliver_daily_digest.delay(restaurant_id, target.isoformat())
    return count


@celery_app.task(name="app.tasks.recommendations.generate_daily_all")
def generate_daily_all() -> int:
    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    for integration in integrations:
        generate_daily.delay(str(integration.restaurant_id))
    return len(integrations)
