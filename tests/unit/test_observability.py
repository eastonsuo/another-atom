from datetime import UTC, datetime

from another_atom.observability import _log_file_path


def test_log_file_name_uses_process_id_and_process_start_time(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("another_atom.observability.os.getpid", lambda: 42)

    path = _log_file_path(tmp_path, datetime(2026, 7, 11, 14, 23, 16, tzinfo=UTC))

    assert path == tmp_path / "atom-42-20260711-142316.log"
