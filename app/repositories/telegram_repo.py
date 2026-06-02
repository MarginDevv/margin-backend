"""Telegram link-token and delivery repositories."""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import delete, select

from app.models.telegram import DeliveryKind, TelegramDelivery, TelegramLinkToken
from app.repositories.base import BaseRepository
from app.utils.datetime import now_utc


class TelegramLinkTokenRepository(BaseRepository[TelegramLinkToken]):
    model = TelegramLinkToken

    async def get_active(self, token: str) -> TelegramLinkToken | None:
        stmt = select(TelegramLinkToken).where(
            TelegramLinkToken.token == token,
            TelegramLinkToken.used_at.is_(None),
            TelegramLinkToken.expires_at > now_utc(),
        )
        return await self.session.scalar(stmt)

    async def purge_expired(self) -> int:
        result = await self.session.execute(
            delete(TelegramLinkToken).where(TelegramLinkToken.expires_at < now_utc())
        )
        return result.rowcount or 0


class TelegramDeliveryRepository(BaseRepository[TelegramDelivery]):
    model = TelegramDelivery

    async def already_sent(
        self,
        restaurant_id: uuid.UUID,
        user_id: uuid.UUID,
        kind: DeliveryKind,
        for_date: date | None,
    ) -> bool:
        stmt = select(TelegramDelivery.id).where(
            TelegramDelivery.restaurant_id == restaurant_id,
            TelegramDelivery.user_id == user_id,
            TelegramDelivery.kind == kind,
            TelegramDelivery.for_date == (for_date.isoformat() if for_date else None),
            TelegramDelivery.sent_at.is_not(None),
        )
        return await self.session.scalar(stmt) is not None
