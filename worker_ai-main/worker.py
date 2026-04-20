from __future__ import annotations

import asyncio
import logging

from client import ReviewSiteClient
from config import get_settings
from logging_setup import correlation_id_ctx, new_correlation_id, setup_logging
from metrics import reviews_failed_total, reviews_processed_total
from models import AIReplyPayload, RemoteReview, ReviewStatus, ReviewTone, ReviewUpdatePayload
from processor import analyze_review
from state import get_worker_state
from telegram_bot import send_new_review_notification

setup_logging()
logger = logging.getLogger("worker")


class ReviewWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = get_worker_state()
        self.client = ReviewSiteClient()
        self._trigger = asyncio.Event()
        self._pending_cids: dict[int, str] = {}

    def trigger(self, review_id: int | None = None, correlation_id: str | None = None) -> None:
        """Внешний вызов (webhook) говорит: «не жди интервал, проверь сейчас».

        Если webhook передал review_id и correlation_id — запомним,
        чтобы при обработке конкретного отзыва использовать тот же cid
        (сквозная трассировка от POST /api/v1/reviews до ответа LLM).
        """
        if review_id is not None and correlation_id:
            self._pending_cids[review_id] = correlation_id
        self._trigger.set()

    async def wait_for_site(self) -> None:
        logger.info("Waiting for target site at %s", self.settings.target_site_url)
        while True:
            try:
                await self.client.check_site()
                logger.info("Target site is ready")
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("Target site is not ready yet: %s", exc)
                await asyncio.sleep(3)

    async def process_one(self, review: RemoteReview) -> None:
        logger.info("Processing review id=%s", review.id)

        if review.is_ai:
            logger.info("Review id=%s is AI-authored, marking as processed", review.id)
            await self.client.update_review(
                review.id,
                ReviewUpdatePayload(status=ReviewStatus.PROCESSED, tone=ReviewTone.NEUTRAL),
            )
            reviews_processed_total.labels(tone="ai").inc()
            return

        analysis = await analyze_review(review.text)
        review.tone = analysis.tone.value

        if not self.state.is_notified(review.id) and await send_new_review_notification(review):
            self.state.mark_notified(review.id)

        await self.client.create_ai_reply(
            AIReplyPayload(
                parent_id=review.id,
                name=self.settings.ai_author_name,
                text=analysis.reply,
            )
        )
        await self.client.update_review(
            review.id,
            ReviewUpdatePayload(
                status=ReviewStatus.PROCESSED,
                tone=analysis.tone,
                response=analysis.reply,
            ),
        )
        reviews_processed_total.labels(tone=analysis.tone.value).inc()
        logger.info("Review id=%s processed (tone=%s)", review.id, analysis.tone.value)

    async def tick(self) -> int:
        reviews = await self.client.claim_new_reviews(limit=10)
        for review in reviews:
            cid = self._pending_cids.pop(review.id, None) or new_correlation_id()
            token = correlation_id_ctx.set(cid)
            try:
                await self.process_one(review)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to process review id=%s: %s", review.id, exc)
                reviews_failed_total.inc()
                try:
                    await self.client.update_review(
                        review.id,
                        ReviewUpdatePayload(
                            status=ReviewStatus.FAILED,
                            last_error=f"{type(exc).__name__}: {exc}"[:500],
                        ),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to mark review id=%s as failed", review.id)
            finally:
                correlation_id_ctx.reset(token)
        return len(reviews)

    async def run(self) -> None:
        await self.wait_for_site()
        logger.info(
            "Worker started (poll interval=%ss, target=%s)",
            self.settings.worker_poll_interval,
            self.settings.target_site_url,
        )
        while True:
            processed = await self.tick()
            if processed:
                logger.info("Processed %s review(s) in current iteration", processed)
            try:
                await asyncio.wait_for(self._trigger.wait(), timeout=self.settings.worker_poll_interval)
            except TimeoutError:
                pass
            finally:
                self._trigger.clear()


async def main() -> None:
    worker = ReviewWorker()

    tasks: list[asyncio.Task] = [asyncio.create_task(worker.run())]

    if worker.settings.enable_webhook:
        from webhook_server import run_webhook_server

        tasks.append(asyncio.create_task(run_webhook_server(worker)))

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
