"""Writeoff repository — upserts and leak-detection aggregations."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.writeoff import Writeoff, WriteoffItem
from app.repositories.base import BaseRepository


class WriteoffRepository(BaseRepository[Writeoff]):
    model = Writeoff

    async def upsert(self, header: dict[str, Any]) -> uuid.UUID:
        stmt = (
            pg_insert(Writeoff)
            .values(header)
            .on_conflict_do_update(
                constraint="uq_writeoff_iiko",
                set_={
                    "occurred_at": header.get("occurred_at"),
                    "store_name": header.get("store_name"),
                    "total_cost": header.get("total_cost"),
                    "comment": header.get("comment"),
                    "iiko_document_number": header.get("iiko_document_number"),
                },
            )
            .returning(Writeoff.id)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def replace_items(
        self, writeoff_id: uuid.UUID, items: list[dict[str, Any]]
    ) -> None:
        await self.session.execute(
            delete(WriteoffItem).where(WriteoffItem.writeoff_id == writeoff_id)
        )
        if items:
            self.session.add_all(
                [WriteoffItem(writeoff_id=writeoff_id, **i) for i in items]
            )
        await self.session.flush()

    async def total_cost_in_range(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
    ) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(Writeoff.total_cost), 0)
        ).where(
            Writeoff.restaurant_id == restaurant_id,
            Writeoff.occurred_at >= start_utc,
            Writeoff.occurred_at < end_utc,
        )
        return Decimal(str(await self.session.scalar(stmt)))

    async def top_writeoff_items(
        self,
        restaurant_id: uuid.UUID,
        start_utc: datetime,
        end_utc: datetime,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                WriteoffItem.name_snapshot.label("name"),
                func.coalesce(func.sum(WriteoffItem.amount), 0).label("amount"),
                func.coalesce(func.sum(WriteoffItem.line_cost), 0).label("cost"),
            )
            .select_from(WriteoffItem)
            .join(Writeoff, Writeoff.id == WriteoffItem.writeoff_id)
            .where(
                Writeoff.restaurant_id == restaurant_id,
                Writeoff.occurred_at >= start_utc,
                Writeoff.occurred_at < end_utc,
            )
            .group_by(WriteoffItem.name_snapshot)
            .order_by(func.sum(WriteoffItem.line_cost).desc())
            .limit(limit)
        )
        return [dict(r._mapping) for r in (await self.session.execute(stmt)).all()]
