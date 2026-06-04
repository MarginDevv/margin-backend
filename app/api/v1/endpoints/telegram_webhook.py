"""Telegram webhook receiver.

Telegram POSTs each update as JSON to /api/v1/webhooks/telegram/{secret}.
We verify both:
  - the secret in the URL path,
  - the `X-Telegram-Bot-Api-Secret-Token` header (set via setWebhook),
then feed the raw JSON into the aiogram dispatcher.

The dispatcher and Bot instance are created lazily and cached at module level —
each request reuses the same Bot session for outbound replies, so we keep one
HTTP keepalive pool instead of opening a fresh client per update.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.core.config import settings
from app.core.logging import get_logger
from app.services.telegram.bot import build_bot, build_dispatcher

logger = get_logger("telegram.webhook")
router = APIRouter()

_bot: Bot | None = None
_dispatcher: Dispatcher | None = None


def _get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = build_bot()
    return _bot


def _get_dispatcher() -> Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = build_dispatcher()
    return _dispatcher


@router.post(
    "/{secret}",
    include_in_schema=False,
    status_code=status.HTTP_200_OK,
)
async def telegram_update(
    secret: str,
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    expected = settings.telegram_webhook_secret
    if not expected:
        logger.error("telegram.webhook.no_secret_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret is not configured",
        )
    # Constant-time-ish comparisons. Both must match.
    if secret != expected or x_telegram_bot_api_secret_token != expected:
        logger.warning("telegram.webhook.secret_mismatch")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad secret")

    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bot token is not configured",
        )

    try:
        payload = await request.json()
    except Exception:
        logger.warning("telegram.webhook.bad_json")
        raise HTTPException(status_code=400, detail="invalid json") from None

    bot = _get_bot()
    dp = _get_dispatcher()
    update = Update.model_validate(payload, context={"bot": bot})

    # Aiogram feeds the update through routers; this awaits until handlers
    # finish so any reply is sent before we respond 200 to Telegram.
    await dp.feed_update(bot, update)
    return {"ok": True}
