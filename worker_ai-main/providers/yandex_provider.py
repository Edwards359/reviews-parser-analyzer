from __future__ import annotations

import logging
from typing import Any

import httpx
from config import get_settings
from models import AnalysisResult
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import build_prompt, parse_llm_response

logger = logging.getLogger("worker.provider.yandex")

YANDEX_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGPTProvider:
    name = "yandex"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.yandex_api_key
        self._folder_id = settings.yandex_folder_id
        self._model = settings.yandex_model

    def _model_uri(self) -> str:
        return f"gpt://{self._folder_id}/{self._model}/latest"

    async def analyze(self, review_text: str) -> AnalysisResult:
        if not self._api_key or not self._folder_id:
            raise RuntimeError("YANDEX_API_KEY / YANDEX_FOLDER_ID is not set")

        prompt = build_prompt(review_text)
        payload: dict[str, Any] = {
            "modelUri": self._model_uri(),
            "completionOptions": {"stream": False, "temperature": 0.3, "maxTokens": 400},
            "messages": [{"role": "user", "text": prompt}],
        }
        headers = {
            "Authorization": f"Api-Key {self._api_key}",
            "Content-Type": "application/json",
        }

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(YANDEX_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                alternatives = data.get("result", {}).get("alternatives", [])
                text = alternatives[0]["message"]["text"] if alternatives else ""
                return parse_llm_response(text.strip(), review_text)
        raise RuntimeError("unreachable")
