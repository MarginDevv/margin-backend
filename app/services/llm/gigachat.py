"""GigaChat (Sber) client.

Docs: https://developers.sber.ru/docs/ru/gigachat/api/overview

Auth flow:
  POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth
    Headers: Authorization: Basic <base64(clientId:clientSecret)>
             RqUID: <uuid4>
    Body: scope=GIGACHAT_API_PERS  (or GIGACHAT_API_CORP)
  → { access_token, expires_at } — Bearer for subsequent calls.

Chat:
  POST https://gigachat.devices.sberbank.ru/api/v1/chat/completions
    Authorization: Bearer <token>
    JSON: { model, messages: [{role, content}], temperature, max_tokens }
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.base import LLMError, LLMMessage, LLMResponse

logger = get_logger("llm.gigachat")


class _TransientError(Exception):
    pass


class GigaChatClient:
    provider_name = "gigachat"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client_id = client_id or settings.gigachat_client_id
        self._client_secret = client_secret or settings.gigachat_client_secret
        self._scope = scope or settings.gigachat_scope
        self._model = model or settings.gigachat_model
        if not (self._client_id and self._client_secret):
            raise LLMError("GIGACHAT_CLIENT_ID / GIGACHAT_CLIENT_SECRET are not set")

        # Sber issues self-signed cert chain — many infra setups need verify=False
        # locally, but we keep it on by default. Override with GIGACHAT_VERIFY_SSL.
        verify = settings.gigachat_verify_ssl
        self._auth = httpx.AsyncClient(
            base_url="https://ngw.devices.sberbank.ru:9443",
            timeout=timeout,
            verify=verify,
        )
        self._api = httpx.AsyncClient(
            base_url="https://gigachat.devices.sberbank.ru/api/v1",
            timeout=timeout,
            verify=verify,
        )
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    async def aclose(self) -> None:
        await self._auth.aclose()
        await self._api.aclose()

    async def __aenter__(self) -> GigaChatClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    # ---- token ----

    async def _ensure_token(self) -> str:
        from datetime import UTC

        now = datetime.now(UTC)
        if (
            self._token
            and self._token_expires_at
            and self._token_expires_at - timedelta(seconds=60) > now
        ):
            return self._token

        basic = base64.b64encode(f"{self._client_id}:{self._client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {basic}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        body = {"scope": self._scope}
        response = await self._auth.post("/api/v2/oauth", headers=headers, data=body)
        if response.status_code >= 400:
            raise LLMError(f"GigaChat oauth failed [{response.status_code}]: {response.text[:300]}")
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise LLMError(f"GigaChat oauth missing access_token: {data}")
        # `expires_at` is in ms since epoch.
        expires_at_ms = data.get("expires_at")
        if isinstance(expires_at_ms, int):
            self._token_expires_at = datetime.fromtimestamp(expires_at_ms / 1000, tz=UTC)
        else:
            self._token_expires_at = now + timedelta(minutes=25)
        self._token = token
        return token

    # ---- chat ----

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 512,
        temperature: float = 0.4,
    ) -> LLMResponse:
        token = await self._ensure_token()
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        retryer = AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((httpx.TransportError, _TransientError)),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                response = await self._api.post("/chat/completions", headers=headers, json=payload)
                if response.status_code == 401:
                    self._token = None
                    token = await self._ensure_token()
                    headers["Authorization"] = f"Bearer {token}"
                    response = await self._api.post(
                        "/chat/completions", headers=headers, json=payload
                    )
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise _TransientError(f"gigachat {response.status_code}: {response.text[:300]}")
                if response.status_code >= 400:
                    raise LLMError(
                        f"gigachat chat failed [{response.status_code}]: " f"{response.text[:300]}"
                    )
                data = response.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                usage = data.get("usage") or {}
                return LLMResponse(
                    text=(msg.get("content") or "").strip(),
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    model=data.get("model") or self._model,
                    provider=self.provider_name,
                )
        raise LLMError("gigachat chat exhausted retries")
