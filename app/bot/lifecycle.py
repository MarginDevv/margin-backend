"""Bot lifecycle: start/stop helpers shared between polling and webhook modes.

In polling mode (`python -m app.bot`) we keep a long-running dispatcher.

In webhook mode:
- Register the URL with Telegram once via `python -m app.bot setup-webhook`.
- Telegram POSTs updates to `/webhooks/telegram/{secret}` on the FastAPI app
  (see app/api/v1/endpoints/telegram_webhook.py). The route feeds raw JSON
  into the dispatcher.
- Run `python -m app.bot delete-webhook` to revert (e.g. before switching
  back to polling).
"""

from __future__ import annotations

from urllib.parse import urljoin

from aiogram import Bot

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import get_logger

logger = get_logger("bot.lifecycle")


def webhook_path() -> str:
    """Path the FastAPI app exposes for Telegram updates.

    We embed the secret in the URL as a defense-in-depth layer on top of the
    `X-Telegram-Bot-Api-Secret-Token` header check.
    """
    secret = settings.telegram_webhook_secret or "no-secret-set"
    return f"/api/v1/webhooks/telegram/{secret}"


def webhook_url() -> str:
    if not settings.telegram_webhook_url:
        raise DomainError(
            "TELEGRAM_WEBHOOK_URL is not configured. Set it to the public HTTPS "
            "origin of this API (e.g. https://api.margin.example).",
            code="webhook_url_missing",
        )
    if not settings.telegram_webhook_secret:
        raise DomainError(
            "TELEGRAM_WEBHOOK_SECRET is not configured. Set it to a long random "
            "string used to verify Telegram payloads.",
            code="webhook_secret_missing",
        )
    return urljoin(settings.telegram_webhook_url.rstrip("/") + "/", webhook_path().lstrip("/"))


async def setup_webhook(bot: Bot) -> None:
    url = webhook_url()
    await bot.set_webhook(
        url=url,
        secret_token=settings.telegram_webhook_secret,
        drop_pending_updates=False,
        allowed_updates=None,  # let aiogram default include all relevant types
    )
    info = await bot.get_webhook_info()
    logger.info("bot.webhook.set", url=url, pending=info.pending_update_count)


async def delete_webhook(bot: Bot, *, drop_pending: bool = False) -> None:
    await bot.delete_webhook(drop_pending_updates=drop_pending)
    logger.info("bot.webhook.deleted", drop_pending=drop_pending)
