"""Optional LLM polish on top of the heuristic recommendation engine.

Heuristics decide WHAT to recommend (with deterministic numbers). The LLM
rewrites the description + action in natural, restaurant-owner-friendly
Russian. If the LLM is unavailable or errors out, we keep the heuristic text
unchanged — recommendations always go through.
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.services.llm.base import LLMClient, LLMError, LLMMessage, NoOpLLM

logger = get_logger("llm.enhancer")

SYSTEM_PROMPT = (
    "Ты — AI-управляющий для российского ресторанного бизнеса. "
    "Тебе дана конкретная рекомендация владельцу: заголовок, факты из данных и "
    "предлагаемое действие. Перепиши описание и действие на ясном деловом "
    "русском языке, как опытный консультант. Сохрани все числа и факты без "
    "изменений. Не добавляй обещаний и не используй маркетинговые штампы. "
    "Ответ строго в JSON: {\"description\": \"...\", \"action\": \"...\"}. "
    "Описание — 2-3 предложения, действие — 1 короткое предложение."
)


class RecommendationEnhancer:
    """Rewrites recommendation copy via LLM. Safe to call when LLM is disabled."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    @property
    def enabled(self) -> bool:
        return self._llm is not None and not isinstance(self._llm, NoOpLLM)

    async def enhance(
        self,
        *,
        title: str,
        description: str,
        action: str,
        restaurant_name: str | None = None,
    ) -> tuple[str, str]:
        """Returns (description, action). Falls back to inputs on any error."""
        if not self.enabled or self._llm is None:
            return description, action

        user_prompt = (
            (f"Ресторан: {restaurant_name}\n" if restaurant_name else "")
            + f"Заголовок рекомендации: {title}\n"
            + f"Исходное описание (содержит факты): {description}\n"
            + f"Исходное действие: {action}"
        )
        try:
            response = await self._llm.chat(
                [
                    LLMMessage("system", SYSTEM_PROMPT),
                    LLMMessage("user", user_prompt),
                ],
                max_tokens=350,
                temperature=0.3,
            )
        except LLMError as exc:
            logger.warning("llm.enhancer.failed", error=str(exc))
            return description, action

        new_description, new_action = _parse_json(response.text)
        return new_description or description, new_action or action


def _parse_json(text: str) -> tuple[str | None, str | None]:
    import json

    raw = text.strip()
    # Strip code fences if model wrapped JSON in ```json ... ```
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    return (
        (data.get("description") or "").strip() or None,
        (data.get("action") or "").strip() or None,
    )
