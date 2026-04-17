from __future__ import annotations

import logging

from config import get_settings
from models import AnalysisResult
from openai import AsyncOpenAI
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import build_prompt, parse_llm_response

logger = logging.getLogger("worker.provider.openai")


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.openai_model
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def analyze(self, review_text: str) -> AnalysisResult:
        prompt = build_prompt(review_text)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                response = await self._client.responses.create(
                    model=self._model,
                    input=prompt,
                )
                text = (response.output_text or "").strip()
                return parse_llm_response(text, review_text)

        raise RuntimeError("unreachable")
