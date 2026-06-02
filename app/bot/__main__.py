"""Telegram bot entrypoint.

Usage:
    python -m app.bot                 # run in TELEGRAM_BOT_MODE (polling | webhook)
    python -m app.bot setup-webhook   # register webhook URL with Telegram
    python -m app.bot delete-webhook  # remove webhook (e.g. before polling)

Polling mode runs a long-lived dispatcher in this process.
Webhook mode does NOT keep a process — Telegram POSTs straight to the FastAPI
app at /api/v1/webhooks/telegram/{secret}. In that case this command just
registers the URL once and exits.
"""
from __future__ import annotations

import asyncio
import sys

from app.bot.lifecycle import delete_webhook, setup_webhook
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.services.telegram.bot import build_bot, build_dispatcher


async def _run_polling() -> None:
    bot = build_bot()
    dp = build_dispatcher()
    logger = get_logger("bot.polling")
    logger.info(
        "bot.start.polling",
        bot_username=settings.telegram_bot_username,
    )
    try:
        # If a webhook was previously set, drop it — polling and webhook are
        # mutually exclusive on the Telegram side.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def _run_setup_webhook() -> None:
    bot = build_bot()
    try:
        await setup_webhook(bot)
    finally:
        await bot.session.close()


async def _run_delete_webhook() -> None:
    bot = build_bot()
    try:
        await delete_webhook(bot, drop_pending=False)
    finally:
        await bot.session.close()


async def main(argv: list[str]) -> None:
    configure_logging()
    logger = get_logger("bot.main")

    if not settings.telegram_bot_token:
        logger.error("bot.start.no_token")
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")

    command = argv[1] if len(argv) > 1 else None

    if command == "setup-webhook":
        await _run_setup_webhook()
        return
    if command == "delete-webhook":
        await _run_delete_webhook()
        return
    if command is not None:
        raise SystemExit(f"Unknown command: {command!r}")

    if settings.telegram_bot_mode == "webhook":
        # Nothing long-running to do — FastAPI handles inbound updates.
        # Register once and exit so docker-compose can either skip the bot
        # service or use it as a one-shot.
        logger.info("bot.mode.webhook.idempotent_setup")
        await _run_setup_webhook()
        return

    await _run_polling()


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
