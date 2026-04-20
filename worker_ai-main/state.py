from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from config import get_settings

logger = logging.getLogger("worker.state")

_lock = threading.Lock()

STATE_VERSION = 2


class WorkerState:
    """Локальный state для идемпотентности Telegram-уведомлений.

    Формат v2 (текущий):
        {
          "version": 2,
          "entries": [{"id": 123, "ts": "2026-04-20T12:00:00+00:00"}, ...]
        }

    Формат v1 (legacy, читается и автоматически мигрируется при первой записи):
        {"notified_review_ids": [1, 2, 3]}

    Ограничения (разумный бюджет, чтобы файл не рос бесконечно):
    - `max_entries`: после добавления записи лишнее обрезается с головы (FIFO).
    - `max_age_days`: записи старше указанного возраста удаляются при
      каждой операции записи. Для мигрированных из v1 записей используется
      время миграции как `ts` (чтобы сразу всё не выбросить).
    """

    def __init__(
        self,
        file_path: str,
        *,
        max_entries: int | None = None,
        max_age_days: int | None = None,
    ) -> None:
        settings = get_settings()
        self.path = Path(file_path)
        self.max_entries = max_entries if max_entries is not None else settings.state_max_entries
        self.max_age_days = (
            max_age_days if max_age_days is not None else settings.state_max_age_days
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": STATE_VERSION, "entries": []})

    # ---------- low-level I/O ----------

    def _read_raw(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return {"version": STATE_VERSION, "entries": []}

    def _write(self, payload: dict[str, Any]) -> None:
        # Атомарная запись: сначала tmp, потом replace, иначе при крэше
        # во время записи потеряем весь файл.
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self.path)

    # ---------- migration ----------

    @staticmethod
    def _migrate_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("version") == STATE_VERSION and "entries" in payload:
            return payload

        ids: list[int] = []
        if "notified_review_ids" in payload and isinstance(payload["notified_review_ids"], list):
            ids = [int(x) for x in payload["notified_review_ids"] if isinstance(x, int)]
        if "entries" in payload and isinstance(payload["entries"], list):
            for item in payload["entries"]:
                if isinstance(item, dict) and "id" in item:
                    ids.append(int(item["id"]))

        now_iso = datetime.now(tz=UTC).isoformat()
        migrated = {
            "version": STATE_VERSION,
            "entries": [{"id": rid, "ts": now_iso} for rid in dict.fromkeys(ids)],
        }
        logger.info("Migrated state file to v%s, entries=%d", STATE_VERSION, len(migrated["entries"]))
        return migrated

    def _read(self) -> dict[str, Any]:
        payload = self._read_raw()
        return self._migrate_to_v2(payload)

    # ---------- pruning ----------

    @staticmethod
    def _parse_ts(raw: Any) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def _prune(self, entries: list[dict[str, Any]]) -> int:
        """Возвращает количество удалённых записей."""
        removed = 0

        if self.max_age_days > 0 and entries:
            cutoff = datetime.now(tz=UTC) - timedelta(days=self.max_age_days)
            kept: list[dict[str, Any]] = []
            for entry in entries:
                ts = self._parse_ts(entry.get("ts"))
                if ts is None or ts >= cutoff:
                    kept.append(entry)
            removed += len(entries) - len(kept)
            entries[:] = kept

        if self.max_entries > 0 and len(entries) > self.max_entries:
            overflow = len(entries) - self.max_entries
            del entries[:overflow]
            removed += overflow

        return removed

    # ---------- public API ----------

    def is_notified(self, review_id: int) -> bool:
        with _lock:
            entries = self._read().get("entries", [])
            return any(e.get("id") == review_id for e in entries)

    def mark_notified(self, review_id: int) -> None:
        with _lock:
            payload = self._read()
            entries: list[dict[str, Any]] = payload.setdefault("entries", [])
            if any(e.get("id") == review_id for e in entries):
                return
            entries.append(
                {"id": review_id, "ts": datetime.now(tz=UTC).isoformat()}
            )
            removed = self._prune(entries)
            if removed:
                logger.info(
                    "Pruned %d stale entr%s from state (now=%d, cap=%d, max_age_days=%d)",
                    removed,
                    "y" if removed == 1 else "ies",
                    len(entries),
                    self.max_entries,
                    self.max_age_days,
                )
            payload["version"] = STATE_VERSION
            self._write(payload)

    def size(self) -> int:
        """Текущее количество записей (для метрик)."""
        return len(self._read().get("entries", []))


def get_worker_state() -> WorkerState:
    settings = get_settings()
    return WorkerState(
        settings.state_file_path,
        max_entries=settings.state_max_entries,
        max_age_days=settings.state_max_age_days,
    )
