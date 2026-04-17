from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from models import AnalysisResult, ReviewTone
from tone import build_fallback_reply, detect_tone

logger = logging.getLogger("worker.provider")


SYSTEM_PROMPT = (
    "Ты — вежливый ассистент службы поддержки. "
    "Тебе приходит текст отзыва клиента. Нужно определить тональность "
    "('positive', 'negative', 'neutral') и сформулировать короткий ответ от лица компании "
    "на том же языке, что и отзыв. Ответ короткий (не более 3 предложений), без шаблонов, "
    "без markdown, без подписи. На негативный отзыв — извинись и предложи помощь, "
    "на позитивный — поблагодари, на нейтральный — вежливо отреагируй по существу."
)


OUTPUT_INSTRUCTION = (
    'Ответь строго валидным JSON-объектом формата: '
    '{"tone": "positive|negative|neutral", "reply": "..."}. '
    "Никакого текста вне JSON."
)


class LLMProvider(Protocol):
    name: str

    async def analyze(self, review_text: str) -> AnalysisResult: ...


def build_prompt(review_text: str) -> str:
    return f"{SYSTEM_PROMPT}\n\n{OUTPUT_INSTRUCTION}\n\nОтзыв: {review_text}"


_JSON_RE = re.compile(r"\{[^\{\}]*\}", flags=re.DOTALL)


def parse_llm_response(raw_text: str, review_text: str) -> AnalysisResult:
    """Пытается распарсить JSON-ответ LLM. Если не получается — fallback по словарю."""
    candidate = raw_text.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        match = _JSON_RE.search(candidate)
        if not match:
            logger.warning("LLM did not return JSON, using fallback: %r", candidate[:200])
            return AnalysisResult(tone=detect_tone(review_text), reply=build_fallback_reply(review_text))
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("LLM JSON parse failed, using fallback")
            return AnalysisResult(tone=detect_tone(review_text), reply=build_fallback_reply(review_text))

    tone_value = str(data.get("tone", "")).lower().strip()
    if tone_value not in {t.value for t in ReviewTone}:
        tone = detect_tone(review_text)
    else:
        tone = ReviewTone(tone_value)

    reply = str(data.get("reply") or "").strip()
    if not reply:
        reply = build_fallback_reply(review_text)
    return AnalysisResult(tone=tone, reply=reply)
