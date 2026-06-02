"""iiko integration repository."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.iiko_integration import IikoIntegration
from app.models.restaurant import Restaurant
from app.repositories.base import BaseRepository


class IikoIntegrationRepository(BaseRepository[IikoIntegration]):
    model = IikoIntegration

    async def get_by_restaurant(self, restaurant_id: uuid.UUID) -> IikoIntegration | None:
        stmt = select(IikoIntegration).where(IikoIntegration.restaurant_id == restaurant_id)
        return await self.session.scalar(stmt)

    async def list_active(self) -> list[IikoIntegration]:
        stmt = select(IikoIntegration).where(IikoIntegration.is_active.is_(True))
        return list((await self.session.scalars(stmt)).all())

    async def list_active_with_restaurant(self) -> list[IikoIntegration]:
        """Active integrations with their `restaurant` eagerly loaded."""
        stmt = (
            select(IikoIntegration)
            .options(joinedload(IikoIntegration.restaurant))
            .join(Restaurant, Restaurant.id == IikoIntegration.restaurant_id)
            .where(
                IikoIntegration.is_active.is_(True),
                Restaurant.is_active.is_(True),
            )
        )
        return list((await self.session.scalars(stmt)).all())
