from __future__ import annotations

import logging

import httpx
from config import get_settings
from models import AIReplyPayload, RemoteReview, ReviewStatus, ReviewUpdatePayload
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger("worker.client")
settings = get_settings()


RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


class ReviewSiteClient:
    def __init__(self) -> None:
        self._base_url = settings.target_site_url.rstrip("/")
        self._worker_headers = {"X-Worker-Token": settings.worker_api_token}

    async def _request(self, method: str, path: str, *, auth: bool = False, **kwargs) -> httpx.Response:
        url = f"{self._base_url}{path}"
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers.update(self._worker_headers)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
            retry=retry_if_exception_type(RETRYABLE),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response
        raise RuntimeError("unreachable")

    async def check_site(self) -> None:
        await self._request("GET", "/healthz")

    async def claim_new_reviews(self, limit: int = 10) -> list[RemoteReview]:
        """Атомарно забирает новые отзывы через v1-эндпоинт /reviews/claim.

        Если сервер не поддерживает claim (404), fallback — фильтрация статуса new.
        """
        try:
            response = await self._request(
                "POST", "/api/v1/reviews/claim", auth=True, params={"limit": limit}
            )
            payload = response.json()
            return [RemoteReview.model_validate(item) for item in payload.get("items", [])]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            logger.info("Server does not support /reviews/claim, fallback to polling")
            return await self._fetch_new_fallback()

    async def _fetch_new_fallback(self) -> list[RemoteReview]:
        response = await self._request("GET", "/api/reviews")
        items = [RemoteReview.model_validate(item) for item in response.json()]
        return [r for r in items if r.status == ReviewStatus.NEW and not r.is_ai]

    async def create_ai_reply(self, payload: AIReplyPayload) -> RemoteReview:
        try:
            response = await self._request(
                "POST",
                "/api/v1/reviews/ai-reply",
                auth=True,
                json=payload.model_dump(mode="json", exclude_none=True),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            logger.info("AI-reply endpoint unavailable, fallback to legacy POST /api/reviews")
            response = await self._request(
                "POST",
                "/api/reviews",
                json=payload.model_dump(mode="json", exclude_none=True),
            )
        logger.info("Created AI reply for parent id=%s", payload.parent_id)
        return RemoteReview.model_validate(response.json())

    async def update_review(self, review_id: int, payload: ReviewUpdatePayload) -> RemoteReview:
        response = await self._request(
            "PATCH",
            f"/api/v1/reviews/{review_id}",
            auth=True,
            json=payload.model_dump(mode="json", exclude_none=True),
        )
        logger.info("Review id=%s updated", review_id)
        return RemoteReview.model_validate(response.json())
