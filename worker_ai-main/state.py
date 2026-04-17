from __future__ import annotations

import json
import threading
from pathlib import Path

from config import get_settings

_lock = threading.Lock()


class WorkerState:
    """Локальный state для идемпотентности Telegram-уведомлений.

    Обработка отзывов перенесена в БД (статусы new/processing/processed),
    здесь остаются только ID уже отправленных в Telegram уведомлений.
    """

    def __init__(self, file_path: str) -> None:
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"notified_review_ids": []})

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"notified_review_ids": []}

    def _write(self, payload: dict) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def is_notified(self, review_id: int) -> bool:
        with _lock:
            return review_id in self._read().get("notified_review_ids", [])

    def mark_notified(self, review_id: int) -> None:
        with _lock:
            payload = self._read()
            ids = payload.setdefault("notified_review_ids", [])
            if review_id not in ids:
                ids.append(review_id)
                self._write(payload)


def get_worker_state() -> WorkerState:
    return WorkerState(get_settings().state_file_path)
