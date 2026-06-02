"""Telegram-related schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class TelegramLinkTokenResponse(BaseModel):
    """Deep-link payload returned to the web client.

    The user clicks the URL → Telegram opens the bot with `/start <token>` →
    the bot links the chat id to the user.
    """
    token: str
    deep_link: str
    expires_at: datetime
    bot_username: str | None


class TelegramStatus(BaseModel):
    linked: bool
    telegram_username: str | None
    chat_id: int | None


class NotificationsUpdate(ORMModel):
    telegram_notifications: bool


class NotificationsRead(ORMModel):
    restaurant_id: str
    telegram_notifications: bool


class ManualDeliveryResponse(BaseModel):
    queued: int
    skipped_no_chat: int
    skipped_already_sent: int
    task_id: str
