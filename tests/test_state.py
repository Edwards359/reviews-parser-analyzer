from pathlib import Path

from state import WorkerState


def test_state_idempotent_notification(tmp_path: Path):
    state = WorkerState(str(tmp_path / "state.json"))
    assert state.is_notified(1) is False
    state.mark_notified(1)
    state.mark_notified(1)
    assert state.is_notified(1) is True
