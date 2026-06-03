"""iiko integration endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import DbSession, require_manager, require_owner
from app.core.exceptions import ConflictError, NotFoundError
from app.models.iiko_integration import IikoIntegration
from app.models.restaurant import Restaurant
from app.repositories.integration_repo import IikoIntegrationRepository
from app.schemas.integration import (
    IikoIntegrationCreate,
    IikoIntegrationRead,
    IikoIntegrationUpdate,
    IikoSyncTriggerResponse,
)
from app.utils.crypto import encrypt_str
from app.utils.datetime import now_utc

router = APIRouter()


@router.get("", response_model=IikoIntegrationRead)
async def get_integration(
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    session: DbSession,
) -> IikoIntegrationRead:
    integration = await IikoIntegrationRepository(session).get_by_restaurant(restaurant.id)
    if not integration:
        raise NotFoundError("iiko integration is not configured")
    return IikoIntegrationRead.model_validate(integration)


@router.post("", response_model=IikoIntegrationRead, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IikoIntegrationCreate,
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> IikoIntegrationRead:
    repo = IikoIntegrationRepository(session)
    if await repo.get_by_restaurant(restaurant.id):
        raise ConflictError("iiko integration already exists for this restaurant")
    integration = IikoIntegration(
        restaurant_id=restaurant.id,
        api_login=encrypt_str(payload.api_login),
        organization_id=payload.organization_id,
    )
    session.add(integration)
    await session.commit()
    await session.refresh(integration)
    return IikoIntegrationRead.model_validate(integration)


@router.patch("", response_model=IikoIntegrationRead)
async def update_integration(
    payload: IikoIntegrationUpdate,
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> IikoIntegrationRead:
    repo = IikoIntegrationRepository(session)
    integration = await repo.get_by_restaurant(restaurant.id)
    if not integration:
        raise NotFoundError("iiko integration is not configured")
    data = payload.model_dump(exclude_unset=True)
    if "api_login" in data and data["api_login"] is not None:
        data["api_login"] = encrypt_str(data["api_login"])
        # Token cache is no longer valid.
        integration.access_token = None
        integration.access_token_expires_at = None
    for k, v in data.items():
        setattr(integration, k, v)
    await session.commit()
    await session.refresh(integration)
    return IikoIntegrationRead.model_validate(integration)


@router.post("/sync", response_model=IikoSyncTriggerResponse, status_code=202)
async def trigger_sync(
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    session: DbSession,
    full: bool = False,
) -> IikoSyncTriggerResponse:
    integration = await IikoIntegrationRepository(session).get_by_restaurant(restaurant.id)
    if not integration or not integration.is_active:
        raise NotFoundError("iiko integration is not configured or inactive")

    from app.tasks.iiko_sync import full_sync_restaurant, incremental_sync_restaurant

    task = (full_sync_restaurant if full else incremental_sync_restaurant).delay(
        str(restaurant.id)
    )
    return IikoSyncTriggerResponse(task_id=task.id, queued_at=now_utc())


@router.delete("", status_code=204)
async def delete_integration(
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> None:
    repo = IikoIntegrationRepository(session)
    integration = await repo.get_by_restaurant(restaurant.id)
    if not integration:
        raise NotFoundError("iiko integration is not configured")
    await repo.delete(integration.id)
    await session.commit()
