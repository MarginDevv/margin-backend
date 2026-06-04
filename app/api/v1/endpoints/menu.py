"""Menu endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import DbSession, require_manager, require_member
from app.core.exceptions import NotFoundError
from app.models.restaurant import Restaurant
from app.repositories.menu_repo import MenuItemRepository
from app.schemas.menu import MenuItemRead, MenuItemUpdate

router = APIRouter()


@router.get("", response_model=list[MenuItemRead])
async def list_menu(
    restaurant: Annotated[Restaurant, Depends(require_member)],
    session: DbSession,
    active_only: bool = False,
) -> list[MenuItemRead]:
    items = await MenuItemRepository(session).list_for_restaurant(
        restaurant.id, active_only=active_only
    )
    return [MenuItemRead.model_validate(i) for i in items]


@router.patch("/{menu_item_id}", response_model=MenuItemRead)
async def update_menu_item(
    menu_item_id: uuid.UUID,
    payload: MenuItemUpdate,
    restaurant: Annotated[Restaurant, Depends(require_manager)],
    session: DbSession,
) -> MenuItemRead:
    repo = MenuItemRepository(session)
    item = await repo.get(menu_item_id)
    if not item or item.restaurant_id != restaurant.id:
        raise NotFoundError("Menu item not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await session.commit()
    await session.refresh(item)
    return MenuItemRead.model_validate(item)
