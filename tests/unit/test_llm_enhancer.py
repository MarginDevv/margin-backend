"""Recommendation enhancer parses LLM JSON and degrades gracefully."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("APP_SECRET_KEY", "x" * 32)
os.environ.setdefault("JWT_SECRET_KEY", "y" * 32)


class _FakeLLM:
    provider_name = "fake"

    def __init__(self, response_text: str) -> None:
        self._text = response_text

    async def chat(self, messages, *, max_tokens=512, temperature=0.4):
        from app.services.llm.base import LLMResponse

        return LLMResponse(text=self._text, provider="fake")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_enhancer_disabled_when_no_llm() -> None:
    from app.services.llm.recommendation_enhancer import RecommendationEnhancer

    enhancer = RecommendationEnhancer(llm=None)
    assert enhancer.enabled is False
    desc, action = await enhancer.enhance(title="t", description="d", action="a")
    assert (desc, action) == ("d", "a")


@pytest.mark.asyncio
async def test_enhancer_uses_llm_json() -> None:
    from app.services.llm.recommendation_enhancer import RecommendationEnhancer

    payload = '{"description": "Новое описание с фактом 12%.", ' '"action": "Поднять цену на 6%."}'
    enhancer = RecommendationEnhancer(llm=_FakeLLM(payload))
    desc, action = await enhancer.enhance(
        title="Поднять цену",
        description="старое",
        action="старое",
        restaurant_name="Кафе",
    )
    assert desc == "Новое описание с фактом 12%."
    assert action == "Поднять цену на 6%."


@pytest.mark.asyncio
async def test_enhancer_strips_code_fence() -> None:
    from app.services.llm.recommendation_enhancer import RecommendationEnhancer

    payload = '```json\n{"description": "ok", "action": "go"}\n```'
    enhancer = RecommendationEnhancer(llm=_FakeLLM(payload))
    desc, action = await enhancer.enhance(title="x", description="d", action="a")
    assert desc == "ok"
    assert action == "go"


@pytest.mark.asyncio
async def test_enhancer_falls_back_on_bad_json() -> None:
    from app.services.llm.recommendation_enhancer import RecommendationEnhancer

    enhancer = RecommendationEnhancer(llm=_FakeLLM("not json at all"))
    desc, action = await enhancer.enhance(title="x", description="orig-desc", action="orig-action")
    assert desc == "orig-desc"
    assert action == "orig-action"
