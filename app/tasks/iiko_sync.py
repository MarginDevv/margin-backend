"""Celery tasks for iiko synchronization."""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.core.logging import get_logger
from app.repositories.integration_repo import IikoIntegrationRepository
from app.services.iiko.sync_service import IikoSyncService
from app.tasks._runner import run_async, with_session
from app.tasks.celery_app import celery_app
from app.utils.datetime import now_utc

logger = get_logger("tasks.iiko_sync")


@celery_app.task(name="app.tasks.iiko_sync.incremental_sync_restaurant", bind=True, max_retries=3)
def incremental_sync_restaurant(self, restaurant_id: str) -> int:
    """15-minute incremental sync for a single restaurant."""
    rid = uuid.UUID(restaurant_id)

    async def _job(session):
        return await IikoSyncService(session).incremental_sync(rid)

    try:
        return run_async(with_session(_job))
    except Exception as exc:
        logger.error("iiko.incremental.failed", restaurant_id=restaurant_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc


@celery_app.task(name="app.tasks.iiko_sync.full_sync_restaurant", bind=True, max_retries=3)
def full_sync_restaurant(self, restaurant_id: str) -> int:
    """Full re-sync of yesterday + nomenclature refresh for a single restaurant."""
    rid = uuid.UUID(restaurant_id)
    yesterday = now_utc() - timedelta(days=1)

    async def _job(session):
        svc = IikoSyncService(session)
        await svc.sync_nomenclature(rid)
        return await svc.full_day_sync(rid, yesterday)

    try:
        return run_async(with_session(_job))
    except Exception as exc:
        logger.error("iiko.full.failed", restaurant_id=restaurant_id, error=str(exc))
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1)) from exc


@celery_app.task(name="app.tasks.iiko_sync.incremental_sync_all")
def incremental_sync_all() -> int:
    """Fan out incremental syncs to every active integration."""

    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    scheduled = 0
    for integration in integrations:
        incremental_sync_restaurant.delay(str(integration.restaurant_id))
        scheduled += 1
    logger.info("iiko.incremental.fanout", scheduled=scheduled)
    return scheduled


@celery_app.task(name="app.tasks.iiko_sync.daily_full_sync_all")
def daily_full_sync_all() -> int:
    """Fan out full daily syncs to every active integration."""

    async def _job(session):
        return await IikoIntegrationRepository(session).list_active()

    integrations = run_async(with_session(_job))
    scheduled = 0
    for integration in integrations:
        full_sync_restaurant.delay(str(integration.restaurant_id))
        scheduled += 1
    logger.info("iiko.full.fanout", scheduled=scheduled)
    return scheduled
