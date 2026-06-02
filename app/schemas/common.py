"""Shared schema primitives."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TimestampedSchema(ORMModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class IdResponse(BaseModel):
    id: uuid.UUID
