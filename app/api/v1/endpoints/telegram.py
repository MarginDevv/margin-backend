"""Telegram link/unlink and per-restaurant subscription endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core.dependencies import (
    CurrentUser,
    DbSession,
    RestaurantContext,
)
from app.core.exceptions import NotFoundError
from app.schemas.telegram import (
    NotificationsRead,
    NotificationsUpdate,
    TelegramLinkTokenResponse,
    TelegramStatus,
)
from app.services.telegram.link_service import TelegramLinkService, build_deep_link

router = APIRouter()


@router.get("/status", response_model=TelegramStatus)
async def status_(user: CurrentUser) -> TelegramStatus:
    return TelegramStatus(
        linked=user.telegram_chat_id is not None,
        telegram_username=user.telegram_username,
        chat_id=user.telegram_chat_id,
    )


@router.post(
    "/link-token",
    response_model=TelegramLinkTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a deep-link the web client opens to link Telegram",
)
async def create_link_token(user: CurrentUser, session: DbSession) -> TelegramLinkTokenResponse:
    token, bot_username = await TelegramLinkService(session).create_token(user)
    return TelegramLinkTokenResponse(
        token=token.token,
        deep_link=build_deep_link(token.token, bot_username),
        expires_at=token.expires_at,
        bot_username=bot_username,
    )


@router.delete("", status_code=204, summary="Unlink Telegram from the current user")
async def unlink(user: CurrentUser, session: DbSession) -> None:
    await TelegramLinkService(session).unlink(user)


@router.get(
    "/notifications/{restaurant_id}",
    response_model=NotificationsRead,
)
async def get_notifications(ctx: RestaurantContext) -> NotificationsRead:
    _, membership = ctx
    return NotificationsRead(
        restaurant_id=str(membership.restaurant_id),
        telegram_notifications=membership.telegram_notifications,
    )


@router.patch(
    "/notifications/{restaurant_id}",
    response_model=NotificationsRead,
    summary="Toggle Telegram notifications for the current user in this restaurant",
)
async def patch_notifications(
    payload: NotificationsUpdate,
    ctx: RestaurantContext,
    session: DbSession,
) -> NotificationsRead:
    restaurant, membership = ctx
    if not restaurant:
        raise NotFoundError("Restaurant not found")
    membership.telegram_notifications = payload.telegram_notifications
    await session.commit()
    await session.refresh(membership)
    return NotificationsRead(
        restaurant_id=str(membership.restaurant_id),
        telegram_notifications=membership.telegram_notifications,
    )
