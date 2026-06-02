"""Generate and consume deep-link tokens for Telegram onboarding."""
from __future__ import annotations

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.models.activity_event import ActivityKind
from app.models.telegram import TelegramLinkToken
from app.models.user import User
from app.repositories.telegram_repo import TelegramLinkTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.activity.event_service import ActivityEventService
from app.utils.datetime import now_utc


class TelegramLinkService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tokens = TelegramLinkTokenRepository(session)
        self.users = UserRepository(session)

    async def create_token(self, user: User) -> tuple[TelegramLinkToken, str | None]:
        if user.telegram_chat_id:
            raise ConflictError("Telegram is already linked. Unlink first to re-link.")
        token = TelegramLinkToken(
            user_id=user.id,
            token=secrets.token_urlsafe(24),
            expires_at=now_utc() + timedelta(minutes=settings.telegram_link_token_ttl_minutes),
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.commit()
        bot_username = settings.telegram_bot_username
        return token, bot_username

    async def consume(
        self,
        token_str: str,
        chat_id: int,
        telegram_username: str | None,
    ) -> User:
        token = await self.tokens.get_active(token_str)
        if not token:
            raise ValidationError("Link token is invalid or has expired")
        user = await self.users.get(token.user_id)
        if not user:
            raise ValidationError("User no longer exists")

        # Reject if the same Telegram chat is already bound to another account.
        if user.telegram_chat_id and user.telegram_chat_id != chat_id:
            raise ConflictError("This user already has a different Telegram linked")

        # If this chat_id was already used by another user, refuse — Telegram is 1:1.
        existing = await self.session.scalar(
            select(User).where(
                User.telegram_chat_id == chat_id,
                User.id != user.id,
            )
        )
        if existing:
            raise ConflictError("This Telegram account is linked to another user")

        user.telegram_chat_id = chat_id
        user.telegram_username = telegram_username
        token.used_at = now_utc()

        events = ActivityEventService(self.session)
        for membership in user.roles:
            await events.emit(
                membership.restaurant_id,
                ActivityKind.TELEGRAM_LINKED,
                title=f"{user.email} привязал Telegram",
                actor_user_id=user.id,
                payload={"telegram_username": telegram_username},
            )

        await self.session.commit()
        return user

    async def unlink(self, user: User) -> None:
        if not user.telegram_chat_id:
            return
        events = ActivityEventService(self.session)
        for membership in user.roles:
            await events.emit(
                membership.restaurant_id,
                ActivityKind.TELEGRAM_UNLINKED,
                title=f"{user.email} отвязал Telegram",
                actor_user_id=user.id,
            )
        user.telegram_chat_id = None
        user.telegram_username = None
        await self.session.commit()


def build_deep_link(token: str, bot_username: str | None) -> str:
    if not bot_username:
        # We still return a placeholder so the web client can show a clear error.
        return f"https://t.me/?start={token}"
    return f"https://t.me/{bot_username.lstrip('@')}?start={token}"
