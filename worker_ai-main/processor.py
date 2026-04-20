from __future__ import annotations

import logging
import time

from metrics import llm_latency_seconds, llm_requests_total
from models import AnalysisResult
from providers import get_provider
from tone import build_fallback_reply, detect_tone

logger = logging.getLogger("worker.processor")


_provider = get_provider()


async def analyze_review(review_text: str) -> AnalysisResult:
    provider_name = getattr(_provider, "name", "unknown")
    start = time.perf_counter()
    try:
        result = await _provider.analyze(review_text)
    except Exception as exc:  # noqa: BLE001
        llm_requests_total.labels(provider=provider_name, outcome="error").inc()
        logger.exception("LLM provider %s failed, using fallback: %s", provider_name, exc)
        llm_requests_total.labels(provider="fallback", outcome="fallback").inc()
        return AnalysisResult(tone=detect_tone(review_text), reply=build_fallback_reply(review_text))
    else:
        llm_requests_total.labels(provider=provider_name, outcome="ok").inc()
        return result
    finally:
        llm_latency_seconds.labels(provider=provider_name).observe(time.perf_counter() - start)
