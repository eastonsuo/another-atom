from datetime import timedelta
from pathlib import Path

from another_atom.sandbox.host import HostSession, sandbox_command
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
