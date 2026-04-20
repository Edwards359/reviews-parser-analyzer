"""Тесты ротации state.json у воркера:

- миграция со старого формата (v1 -> v2) без потери id;
- FIFO-обрезка при превышении `max_entries`;
- удаление записей старше `max_age_days`;
- атомарная запись (.tmp -> rename);
- выключение лимита нулём.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from state import STATE_VERSION, WorkerState


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fresh_state_is_v2(tmp_path: Path):
    s = WorkerState(str(tmp_path / "state.json"), max_entries=10, max_age_days=30)
    assert s.size() == 0
    raw = _read(s.path)
    assert raw["version"] == STATE_VERSION
    assert raw["entries"] == []


def test_is_notified_false_then_true(tmp_path: Path):
    s = WorkerState(str(tmp_path / "state.json"), max_entries=10, max_age_days=30)
    assert s.is_notified(1) is False
    s.mark_notified(1)
    assert s.is_notified(1) is True


def test_mark_notified_is_idempotent(tmp_path: Path):
    s = WorkerState(str(tmp_path / "state.json"), max_entries=10, max_age_days=30)
    s.mark_notified(42)
    s.mark_notified(42)
    s.mark_notified(42)
    assert s.size() == 1


def test_legacy_v1_format_is_migrated(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"notified_review_ids": [1, 2, 3, 3]}),
        encoding="utf-8",
    )

    s = WorkerState(str(path), max_entries=100, max_age_days=365)
    assert s.is_notified(1) is True
    assert s.is_notified(2) is True
    assert s.is_notified(3) is True
    assert s.is_notified(4) is False

    s.mark_notified(4)
    raw = _read(path)
    assert raw["version"] == STATE_VERSION
    assert [e["id"] for e in raw["entries"]] == [1, 2, 3, 4]
    for entry in raw["entries"]:
        assert "ts" in entry


def test_max_entries_evicts_oldest_fifo(tmp_path: Path):
    s = WorkerState(str(tmp_path / "state.json"), max_entries=3, max_age_days=365)
    for rid in range(1, 6):
        s.mark_notified(rid)

    assert s.size() == 3
    assert s.is_notified(1) is False
    assert s.is_notified(2) is False
    assert s.is_notified(3) is True
    assert s.is_notified(4) is True
    assert s.is_notified(5) is True


def test_max_age_evicts_stale(tmp_path: Path):
    path = tmp_path / "state.json"
    stale_ts = (datetime.now(tz=UTC) - timedelta(days=40)).isoformat()
    fresh_ts = datetime.now(tz=UTC).isoformat()
    path.write_text(
        json.dumps(
            {
                "version": STATE_VERSION,
                "entries": [
                    {"id": 1, "ts": stale_ts},
                    {"id": 2, "ts": stale_ts},
                    {"id": 3, "ts": fresh_ts},
                ],
            }
        ),
        encoding="utf-8",
    )

    s = WorkerState(str(path), max_entries=100, max_age_days=30)
    s.mark_notified(4)

    assert s.is_notified(1) is False
    assert s.is_notified(2) is False
    assert s.is_notified(3) is True
    assert s.is_notified(4) is True


def test_zero_disables_limit(tmp_path: Path):
    s = WorkerState(str(tmp_path / "state.json"), max_entries=0, max_age_days=0)
    for rid in range(1, 50):
        s.mark_notified(rid)
    assert s.size() == 49


def test_write_is_atomic_uses_tmp(tmp_path: Path, monkeypatch):
    """Проверяем, что во время write создаётся временный файл, затем replace.
    Делаем это через перехват Path.replace и проверку, что source — *.tmp.
    """
    s = WorkerState(str(tmp_path / "state.json"), max_entries=10, max_age_days=30)

    observed: list[str] = []

    from pathlib import Path as _Path

    original_replace = _Path.replace

    def tracking_replace(self, target):
        observed.append(self.name)
        return original_replace(self, target)

    monkeypatch.setattr(_Path, "replace", tracking_replace)
    s.mark_notified(777)

    assert observed, "атомарная запись должна использовать .tmp + replace"
    assert all(name.endswith(".tmp") for name in observed)


def test_corrupted_file_falls_back_to_empty(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text("{{{ not a json", encoding="utf-8")

    s = WorkerState(str(path), max_entries=10, max_age_days=30)
    assert s.is_notified(1) is False

    s.mark_notified(1)
    raw = _read(path)
    assert raw["version"] == STATE_VERSION
    assert [e["id"] for e in raw["entries"]] == [1]
