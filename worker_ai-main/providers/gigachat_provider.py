from __future__ import annotations

import base64
import logging
import time
import uuid
from typing import Any

import httpx
from config import get_settings
from models import AnalysisResult
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .base import build_prompt, parse_llm_response

logger = logging.getLogger("worker.provider.gigachat")


AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class GigaChatProvider:
    """Минимальная реализация вызова GigaChat.

    Требуется переменная GIGACHAT_CREDENTIALS — строка формата "client_id:client_secret"
    (или уже закодированный base64; поддерживаем оба варианта).
    """

    name = "gigachat"

    def __init__(self) -> None:
        settings = get_settings()
        self._creds = settings.gigachat_credentials
        self._scope = settings.gigachat_scope
        self._model = settings.gigachat_model
        self._access_token: str | None = None
        self._expires_at: float = 0.0

    def _authorization_header(self) -> str:
        creds = self._creds.strip()
        encoded = (
            base64.b64encode(creds.encode("utf-8")).decode("ascii") if ":" in creds else creds
        )
        return f"Basic {encoded}"

    async def _fetch_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 30:
            return self._access_token

        headers = {
            "Authorization": self._authorization_header(),
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            response = await client.post(AUTH_URL, headers=headers, data={"scope": self._scope})
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        self._access_token = payload["access_token"]
        expires_in = int(payload.get("expires_at", 0))
        self._expires_at = expires_in / 1000 if expires_in > 1e12 else time.time() + 25 * 60
        return self._access_token

    async def analyze(self, review_text: str) -> AnalysisResult:
        if not self._creds:
            raise RuntimeError("GIGACHAT_CREDENTIALS is not set")

        prompt = build_prompt(review_text)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                token = await self._fetch_token()
                async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                    response = await client.post(
                        CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self._model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.3,
                        },
                    )
                response.raise_for_status()
                data = response.json()
                text = (data["choices"][0]["message"]["content"] or "").strip()
                return parse_llm_response(text, review_text)
        raise RuntimeError("unreachable")
