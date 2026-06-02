"""Menu item repository."""
from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.menu_item import MenuItem
from app.repositories.base import BaseRepository


class MenuItemRepository(BaseRepository[MenuItem]):
    model = MenuItem

    async def list_for_restaurant(
        self, restaurant_id: uuid.UUID, *, active_only: bool = False
    ) -> list[MenuItem]:
        stmt = select(MenuItem).where(MenuItem.restaurant_id == restaurant_id)
        if active_only:
            stmt = stmt.where(MenuItem.is_active.is_(True))
        stmt = stmt.order_by(MenuItem.name)
        return list((await self.session.scalars(stmt)).all())

    async def get_by_iiko_id(
        self, restaurant_id: uuid.UUID, iiko_product_id: str
    ) -> MenuItem | None:
        stmt = select(MenuItem).where(
            MenuItem.restaurant_id == restaurant_id,
            MenuItem.iiko_product_id == iiko_product_id,
        )
        return await self.session.scalar(stmt)

    async def upsert_many(self, rows: Iterable[dict]) -> int:
        """Bulk upsert by (restaurant_id, iiko_product_id)."""
        rows = list(rows)
        if not rows:
            return 0
        stmt = insert(MenuItem).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_menu_item_iiko",
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "unit": stmt.excluded.unit,
                "sale_price": stmt.excluded.sale_price,
                "food_cost": stmt.excluded.food_cost,
                "tax_rate": stmt.excluded.tax_rate,
                "is_active": stmt.excluded.is_active,
            },
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
