"""iiko integration schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel, TimestampedSchema


class IikoIntegrationCreate(ORMModel):
    api_login: str = Field(min_length=10)
    organization_id: str | None = None
    terminal_group_id: str | None = None


class IikoIntegrationUpdate(ORMModel):
    api_login: str | None = Field(default=None, min_length=10)
    organization_id: str | None = None
    terminal_group_id: str | None = None
    is_active: bool | None = None


class IikoIntegrationRead(TimestampedSchema):
    organization_id: str | None
    terminal_group_id: str | None
    is_active: bool
    last_sync_at: datetime | None
    last_sync_error: str | None


class IikoSyncTriggerResponse(ORMModel):
    task_id: str
    queued_at: datetime
