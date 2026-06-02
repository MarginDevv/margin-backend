"""Provider-agnostic LLM client interface.

Concrete impls (GigaChat, YandexGPT) implement `chat`. Callers should not depend
on a specific provider — everything goes through `get_llm()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.exceptions import DomainError


class LLMError(DomainError):
    code = "llm_error"


Role = Literal["system", "user", "assistant"]


@dataclass(slots=True)
class LLMMessage:
    role: Role
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None
    provider: str | None = None


class LLMClient(Protocol):
    provider_name: str

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 512,
        temperature: float = 0.4,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...


class NoOpLLM:
    """Fallback used when no provider is configured.

    `chat` raises so callers can degrade gracefully — typically by falling back
    to deterministic templates.
    """
    provider_name = "noop"

    async def chat(
        self,
        messages: list[LLMMessage],
        *,
        max_tokens: int = 512,
        temperature: float = 0.4,
    ) -> LLMResponse:
        raise LLMError("LLM is not configured")

    async def aclose(self) -> None:
        return None
