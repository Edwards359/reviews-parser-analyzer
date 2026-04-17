from __future__ import annotations

from models import AnalysisResult
from tone import build_fallback_reply, detect_tone


class FallbackProvider:
    name = "fallback"

    async def analyze(self, review_text: str) -> AnalysisResult:
        return AnalysisResult(tone=detect_tone(review_text), reply=build_fallback_reply(review_text))
