"""FastAPI dependency injection: auth, RBAC, current restaurant."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Path
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import decode_token
from app.models.restaurant import Restaurant
from app.models.user import User
from app.models.user_restaurant_role import Role, UserRestaurantRole
from app.repositories.restaurant_repo import (
    RestaurantRepository,
    UserRestaurantRoleRepository,
)
from app.repositories.user_repo import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: DbSession,
) -> User:
    if not token:
        raise AuthenticationError("Missing authorization token")
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise AuthenticationError(str(exc)) from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Not an access token")
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing subject")
    user = await UserRepository(session).get(uuid.UUID(user_id))
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_restaurant(
    restaurant_id: Annotated[uuid.UUID, Path(...)],
    user: CurrentUser,
    session: DbSession,
) -> tuple[Restaurant, UserRestaurantRole]:
    """Resolve restaurant by path id and verify membership."""
    restaurant = await RestaurantRepository(session).get(restaurant_id)
    if not restaurant or not restaurant.is_active:
        raise NotFoundError("Restaurant not found")
    if user.is_superuser:
        # Superusers have access; synthesize an owner-equivalent role.
        synthetic = UserRestaurantRole(
            user_id=user.id, restaurant_id=restaurant.id, role=Role.OWNER
        )
        return restaurant, synthetic
    role = await UserRestaurantRoleRepository(session).get_role(user.id, restaurant_id)
    if not role:
        raise PermissionDeniedError("You don't have access to this restaurant")
    return restaurant, role


RestaurantContext = Annotated[
    tuple[Restaurant, UserRestaurantRole], Depends(get_current_restaurant)
]


def require_role(*allowed: Role):
    """Factory: dependency that enforces a minimum role set."""

    async def _dep(ctx: RestaurantContext) -> Restaurant:
        restaurant, role_link = ctx
        if role_link.role not in allowed:
            raise PermissionDeniedError(
                f"Requires one of roles: {', '.join(r.value for r in allowed)}"
            )
        return restaurant

    return _dep


require_owner = require_role(Role.OWNER)
require_manager = require_role(Role.OWNER, Role.MANAGER)
require_member = require_role(Role.OWNER, Role.MANAGER, Role.STAFF)


async def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    return idempotency_key
