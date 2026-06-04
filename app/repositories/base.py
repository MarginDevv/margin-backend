"""Generic async repository."""

from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import TimestampedBase

ModelT = TypeVar("ModelT", bound=TimestampedBase)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelT, **fields: Any) -> ModelT:
        for k, v in fields.items():
            if v is not None:
                setattr(entity, k, v)
        await self.session.flush()
        return entity

    async def delete(self, entity_id: uuid.UUID) -> None:
        await self.session.execute(delete(self.model).where(self.model.id == entity_id))
