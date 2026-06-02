"""Entrypoint for the Telegram bot worker (long-polling).

Run: `python -m app.bot` or via docker-compose service `bot`.
For webhook mode, run uvicorn against `app/bot/webhook.py` instead (TBD).
"""
from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.services.telegram.bot import build_bot, build_dispatcher


async def main() -> None:
    configure_logging()
    logger = get_logger("bot.main")

    if not settings.telegram_bot_token:
        logger.error("bot.start.no_token")
        raise SystemExit("TELEGRAM_BOT_TOKEN is not configured")

    bot = build_bot()
    dp = build_dispatcher()

    if settings.telegram_bot_mode == "webhook":
        logger.error("bot.start.webhook_not_implemented")
        raise SystemExit("Webhook mode is not implemented yet; use polling")

    logger.info(
        "bot.start.polling",
        bot_username=settings.telegram_bot_username,
        mode="polling",
    )
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
