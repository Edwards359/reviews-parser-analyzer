from __future__ import annotations

import logging

from models import AnalysisResult
from providers import get_provider
from tone import build_fallback_reply, detect_tone

logger = logging.getLogger("worker.processor")


_provider = get_provider()


async def analyze_review(review_text: str) -> AnalysisResult:
    try:
        return await _provider.analyze(review_text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM provider %s failed, using fallback: %s", _provider.name, exc)
        return AnalysisResult(tone=detect_tone(review_text), reply=build_fallback_reply(review_text))
