from __future__ import annotations

import asyncio
import logging

from client import ReviewSiteClient
from config import get_settings
from models import AIReplyPayload, RemoteReview, ReviewStatus, ReviewTone, ReviewUpdatePayload
from processor import analyze_review
from state import get_worker_state
from telegram_bot import send_new_review_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("worker")


class ReviewWorker:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.state = get_worker_state()
        self.client = ReviewSiteClient()
        self._trigger = asyncio.Event()

    def trigger(self) -> None:
        """Внешний вызов (webhook) говорит: «не жди интервал, проверь сейчас»."""
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
        logger.info("Review id=%s processed (tone=%s)", review.id, analysis.tone.value)

    async def tick(self) -> int:
        reviews = await self.client.claim_new_reviews(limit=10)
        for review in reviews:
            try:
                await self.process_one(review)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to process review id=%s: %s", review.id, exc)
                try:
                    await self.client.update_review(
                        review.id,
                        ReviewUpdatePayload(status=ReviewStatus.FAILED),
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to mark review id=%s as failed", review.id)
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
