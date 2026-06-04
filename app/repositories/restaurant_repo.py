"""Restaurant repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.restaurant import Restaurant
from app.models.user_restaurant_role import Role, UserRestaurantRole
from app.repositories.base import BaseRepository


class RestaurantRepository(BaseRepository[Restaurant]):
    model = Restaurant

    async def list_for_user(self, user_id: uuid.UUID) -> list[Restaurant]:
        stmt = (
            select(Restaurant)
            .join(UserRestaurantRole, UserRestaurantRole.restaurant_id == Restaurant.id)
            .where(UserRestaurantRole.user_id == user_id)
            .order_by(Restaurant.created_at.desc())
        )
        return list((await self.session.scalars(stmt)).all())


class UserRestaurantRoleRepository(BaseRepository[UserRestaurantRole]):
    model = UserRestaurantRole

    async def get_role(
        self, user_id: uuid.UUID, restaurant_id: uuid.UUID
    ) -> UserRestaurantRole | None:
        stmt = select(UserRestaurantRole).where(
            UserRestaurantRole.user_id == user_id,
            UserRestaurantRole.restaurant_id == restaurant_id,
        )
        return await self.session.scalar(stmt)

    async def list_members(self, restaurant_id: uuid.UUID) -> list[UserRestaurantRole]:
        stmt = select(UserRestaurantRole).where(UserRestaurantRole.restaurant_id == restaurant_id)
        return list((await self.session.scalars(stmt)).all())

    async def assign(
        self, user_id: uuid.UUID, restaurant_id: uuid.UUID, role: Role
    ) -> UserRestaurantRole:
        existing = await self.get_role(user_id, restaurant_id)
        if existing:
            existing.role = role
            await self.session.flush()
            return existing
        entity = UserRestaurantRole(user_id=user_id, restaurant_id=restaurant_id, role=role)
        return await self.add(entity)
