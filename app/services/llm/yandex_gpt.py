"""YandexGPT client.

Docs: https://yandex.cloud/ru/docs/foundation-models/text-generation/api-ref/

POST https://llm.api.cloud.yandex.net/foundationModels/v1/completion
  Authorization: Api-Key <api_key>     (or Bearer <iam_token>)
  Body: {
    "modelUri": "gpt://<folder_id>/yandexgpt-lite/latest",
    "completionOptions": {"stream": false, "temperature": 0.4, "maxTokens": 512},
    "messages": [{"role": "system|user|assistant", "text": "..."}]
  }
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
from app.core.logging import get_logger
from app.services.llm.base import LLMError, LLMMessage, LLMResponse

logger = get_logger("llm.yandex")


class _TransientError(Exception):
    pass


class YandexGPTClient:
    provider_name = "yandex_gpt"

    def __init__(
        self,
        api_key: str | None = None,
        folder_id: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or settings.yandex_gpt_api_key
        self._folder_id = folder_id or settings.yandex_gpt_folder_id
        self._model = model or settings.yandex_gpt_model
        if not (self._api_key and self._folder_id):
            raise LLMError("YANDEX_GPT_API_KEY / YANDEX_GPT_FOLDER_ID are not set")
        self._client = httpx.AsyncClient(
            base_url="https://llm.api.cloud.yandex.net",
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> YandexGPTClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    @property
    def _model_uri(self) -> str:
        return f"gpt://{self._folder_id}/{self._model}/latest"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 512,
        temperature: float = 0.4,
    ) -> LLMResponse:
        payload = {
            "modelUri": self._model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": max_tokens,
            },
            "messages": [{"role": m.role, "text": m.content} for m in messages],
        }
        headers = {
            "Authorization": f"Api-Key {self._api_key}",
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
                response = await self._client.post(
                    "/foundationModels/v1/completion",
                    headers=headers,
                    json=payload,
                )
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    raise _TransientError(
                        f"yandex {response.status_code}: {response.text[:300]}"
                    )
                if response.status_code >= 400:
                    raise LLMError(
                        f"yandex chat failed [{response.status_code}]: "
                        f"{response.text[:300]}"
                    )
                data = response.json()
                result = data.get("result") or {}
                alternatives = result.get("alternatives") or [{}]
                message = alternatives[0].get("message") or {}
                usage = result.get("usage") or {}
                return LLMResponse(
                    text=(message.get("text") or "").strip(),
                    prompt_tokens=int(usage.get("inputTextTokens") or 0) or None,
                    completion_tokens=int(usage.get("completionTokens") or 0) or None,
                    model=result.get("modelVersion") or self._model,
                    provider=self.provider_name,
                )
        raise LLMError("yandex chat exhausted retries")
