from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from another_atom.config import get_settings
from another_atom.repository.service import initialize_repository
from another_atom.sandbox.host import (
    SESSIONS,
    HostSession,
    create_sandbox_host,
    sandbox_command,
)
from another_atom.storage.models import now_utc


def test_sandbox_command_is_non_root_networkless_and_resource_bounded() -> None:
    command = sandbox_command(
        HostSession(
            id="session",
            project_id="00000000-0000-0000-0000-000000000000",
            token="token",
            worktree=Path("/tmp/worktree"),
            expires_at=now_utc() + timedelta(minutes=5),
        )
    )
    joined = " ".join(command)
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--pids-limit=64" in command
    assert "--memory=256m" in command
    assert "--cpus=0.5" in command
    assert "--user=" in joined
    assert " vim -Z -n " in f" {joined} "
    assert "/workspace/app-spec.json" in command


def test_sandbox_host_hides_git_metadata_and_removes_worktree(tmp_path, monkeypatch) -> None:
    secret = "sandbox-test-secret"
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    monkeypatch.setenv("SANDBOX_WORKTREE_ROOT", str(tmp_path / "worktrees"))
    monkeypatch.setenv("SANDBOX_SHARED_SECRET", secret)
    get_settings.cache_clear()
    project_id = str(uuid4())
    initialize_repository(project_id)
    client = TestClient(create_sandbox_host())
    headers = {"Authorization": f"Bearer {secret}"}
    try:
        assert client.post("/v1/sessions", json={"project_id": project_id}).status_code == 401
        created = client.post(
            "/v1/sessions",
            headers=headers,
            json={"project_id": project_id},
        )
        assert created.status_code == 200, created.text
        session_id = created.json()["session_id"]
        worktree = SESSIONS[session_id].worktree
        assert worktree.is_dir()
        assert not (worktree / ".git").exists()

        closed = client.delete(f"/v1/sessions/{session_id}", headers=headers)
        assert closed.status_code == 200, closed.text
        assert session_id not in SESSIONS
        assert not worktree.exists()
    finally:
        SESSIONS.clear()
        get_settings.cache_clear()
