"""Restaurant CRUD + membership management."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import (
    CurrentUser,
    DbSession,
    RestaurantContext,
    require_owner,
)
from app.core.exceptions import ConflictError, NotFoundError
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from app.models.user_restaurant_role import Role, UserRestaurantRole
from app.repositories.restaurant_repo import (
    RestaurantRepository,
    UserRestaurantRoleRepository,
)
from app.repositories.user_repo import UserRepository
from app.schemas.restaurant import (
    MemberInvite,
    MemberRead,
    RestaurantCreate,
    RestaurantRead,
    RestaurantUpdate,
)

router = APIRouter()


@router.get("", response_model=list[RestaurantRead])
async def list_my_restaurants(user: CurrentUser, session: DbSession) -> list[RestaurantRead]:
    items = await RestaurantRepository(session).list_for_user(user.id)
    return [RestaurantRead.model_validate(r) for r in items]


@router.post("", response_model=RestaurantRead, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    payload: RestaurantCreate, user: CurrentUser, session: DbSession
) -> RestaurantRead:
    data = payload.model_dump()
    referral_code = data.pop("referral_code", None)
    restaurant = Restaurant(**data)
    session.add(restaurant)
    await session.flush()
    if referral_code:
        from app.services.referral.referral_service import ReferralService

        await ReferralService(session).attach_referrer(restaurant, referral_code)
    session.add(
        UserRestaurantRole(
            user_id=user.id, restaurant_id=restaurant.id, role=Role.OWNER
        )
    )
    session.add(
        Subscription(
            restaurant_id=restaurant.id,
            plan=SubscriptionPlan.FREE_TRIAL,
            status=SubscriptionStatus.TRIAL,
        )
    )
    await session.commit()
    await session.refresh(restaurant)
    return RestaurantRead.model_validate(restaurant)


@router.get("/{restaurant_id}", response_model=RestaurantRead)
async def get_restaurant(ctx: RestaurantContext) -> RestaurantRead:
    restaurant, _ = ctx
    return RestaurantRead.model_validate(restaurant)


@router.patch("/{restaurant_id}", response_model=RestaurantRead)
async def update_restaurant(
    payload: RestaurantUpdate,
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> RestaurantRead:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(restaurant, field, value)
    await session.commit()
    await session.refresh(restaurant)
    return RestaurantRead.model_validate(restaurant)


@router.get("/{restaurant_id}/members", response_model=list[MemberRead])
async def list_members(
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> list[MemberRead]:
    rows = await UserRestaurantRoleRepository(session).list_members(restaurant.id)
    return [MemberRead.model_validate(r) for r in rows]


@router.post("/{restaurant_id}/members", response_model=MemberRead, status_code=201)
async def add_member(
    payload: MemberInvite,
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> MemberRead:
    user = await UserRepository(session).get_by_email(payload.user_email.lower())
    if not user:
        raise NotFoundError("User with this email not found")
    if payload.role == Role.OWNER:
        # Allow multiple owners only via explicit superuser path — block here for safety.
        raise ConflictError("Cannot assign 'owner' role via invite; transfer ownership instead")
    link = await UserRestaurantRoleRepository(session).assign(
        user.id, restaurant.id, payload.role
    )
    await session.commit()
    return MemberRead.model_validate(link)


@router.delete("/{restaurant_id}/members/{user_id}", status_code=204)
async def remove_member(
    user_id: uuid.UUID,
    restaurant: Annotated[Restaurant, Depends(require_owner)],
    session: DbSession,
) -> None:
    repo = UserRestaurantRoleRepository(session)
    link = await repo.get_role(user_id, restaurant.id)
    if not link:
        raise NotFoundError("Membership not found")
    if link.role == Role.OWNER:
        raise ConflictError("Cannot remove an owner; transfer ownership first")
    await repo.delete(link.id)
    await session.commit()
