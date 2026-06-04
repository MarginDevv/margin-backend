"""Choose an LLM provider based on settings.

Usage:
    async with get_llm() as llm:
        result = await llm.chat([LLMMessage("user", "...")])
"""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.services.llm.base import LLMClient, NoOpLLM

logger = get_logger("llm.factory")


def get_llm() -> LLMClient:
    provider = (settings.llm_provider or "").strip().lower()
    if provider == "gigachat":
        from app.services.llm.gigachat import GigaChatClient

        return GigaChatClient()
    if provider in {"yandex", "yandex_gpt", "yandexgpt"}:
        from app.services.llm.yandex_gpt import YandexGPTClient

        return YandexGPTClient()
    if provider in {"", "noop", "none", "off"}:
        return NoOpLLM()
    logger.warning("llm.provider.unknown", provider=provider)
    return NoOpLLM()
