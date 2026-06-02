"""Outbound Telegram Bot API client (just sendMessage for now).

The aiogram dispatcher (services/telegram/bot.py) is a separate concern — this
module is used by Celery workers / FastAPI to push messages without spinning up
a full bot framework.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import get_logger

logger = get_logger("telegram.client")


class TelegramApiError(DomainError):
    code = "telegram_api_error"


class TelegramRecipientError(DomainError):
    """Recipient-specific: blocked us, chat deleted, etc. Should NOT retry."""
    code = "telegram_recipient_error"


class _TransientError(Exception):
    pass


_PERMANENT_DESCRIPTIONS = (
    "bot was blocked",
    "user is deactivated",
    "chat not found",
    "bot can't initiate conversation",
)


class TelegramClient:
    def __init__(self, bot_token: str | None = None, timeout: float = 15.0) -> None:
        self._token = bot_token or settings.telegram_bot_token
        if not self._token:
            raise TelegramApiError("TELEGRAM_BOT_TOKEN is not configured")
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{self._token}",
            timeout=timeout,
        )

    async def __aenter__(self) -> "TelegramClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
        disable_notification: bool = False,
        reply_markup: dict | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
            "disable_notification": disable_notification,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self._post("sendMessage", payload)

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        retryer = AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TransportError, _TransientError)),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                response = await self._client.post(f"/{method}", json=payload)
                data = response.json()
                if response.status_code == 429:
                    raise _TransientError(f"rate limited: {data}")
                if 500 <= response.status_code < 600:
                    raise _TransientError(f"telegram {method} {response.status_code}: {data}")
                if not data.get("ok"):
                    description = (data.get("description") or "").lower()
                    if any(p in description for p in _PERMANENT_DESCRIPTIONS):
                        raise TelegramRecipientError(data.get("description") or "recipient unavailable")
                    raise TelegramApiError(f"{method}: {data.get('description') or data}")
                return data.get("result", {})  # type: ignore[no-any-return]
        raise TelegramApiError(f"{method}: retries exhausted")
