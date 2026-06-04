"""iiko integration schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel, TimestampedSchema


class IikoIntegrationCreate(ORMModel):
    # /api/v2/access_token credentials — see app/models/iiko_integration.py.
    api_key: str = Field(min_length=10)
    app_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=10)
    organization_id: str | None = None


class IikoIntegrationUpdate(ORMModel):
    api_key: str | None = Field(default=None, min_length=10)
    app_id: str | None = Field(default=None, min_length=1)
    client_secret: str | None = Field(default=None, min_length=10)
    organization_id: str | None = None
    is_active: bool | None = None


class IikoIntegrationRead(TimestampedSchema):
    # Sensitive fields (api_key, client_secret, app_id) are intentionally
    # NOT echoed back — read-side payload only exposes non-secret state.
    organization_id: str | None
    is_active: bool
    last_sync_at: datetime | None
    last_sync_error: str | None


class IikoSyncTriggerResponse(ORMModel):
    task_id: str
    queued_at: datetime
