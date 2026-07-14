import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient

from another_atom.api.dependencies import get_sandbox
from another_atom.contracts.schemas import AppSpec
from another_atom.repository import service as repository_service
from another_atom.sandbox.client import RemoteSandboxSession
from another_atom.storage.database import init_database
from another_atom.storage.models import (
    FileSaveOperation,
    Project,
    ProjectVersion,
    RunEvent,
    now_utc,
)


def _built_run(
    client: TestClient,
    headers: dict | None = None,
    prompt: str = "Build a product catalog",
) -> dict:
    initial = client.post(
        "/api/runs",
        json={"prompt": prompt, "mode": "team"},
        headers=headers,
    ).json()
    run = client.get(f"/api/runs/{initial['run_id']}", headers=headers).json()
    approved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
        headers=headers,
    )
    assert approved.status_code == 202, approved.text
    return client.get(f"/api/runs/{initial['run_id']}", headers=headers).json()


def test_project_versions_map_to_git_commits(client: TestClient) -> None:
    run = _built_run(client)
    first = client.get(f"/api/projects/{run['project_id']}/versions").json()[0]
    edited = client.post(
        f"/api/projects/{run['project_id']}/revisions",
        json={"hero_title": "A committed edit"},
    ).json()
    restored = client.post(f"/api/projects/{run['project_id']}/restore/{first['id']}").json()
    assert len({first["git_commit"], edited["git_commit"], restored["git_commit"]}) == 3

    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        assert project is not None and project.repository_path is not None
        log = subprocess.run(
            ["git", "-C", project.repository_path, "log", "--format=%H"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    assert first["git_commit"] in log
    assert edited["git_commit"] in log
    assert restored["git_commit"] in log


def test_generated_app_javascript_contains_the_loopback_guard(client: TestClient) -> None:
    run = _built_run(client, prompt="给我一个网页版扫雷游戏")
    source = client.get(
        f"/api/projects/{run['project_id']}/files/content",
        params={"path": "app.js", "source": "repository"},
    )

    assert source.status_code == 200
    content = source.json()["content"]
    assert "Localhost and loopback network access is blocked" in content
    assert "window.fetch" in content


def test_database_startup_backfills_repository_for_existing_project(
    client: TestClient,
) -> None:
    run = _built_run(client)
    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        version = db.get(ProjectVersion, run["version_id"])
        assert project is not None and version is not None
        project.repository_path = None
        version.git_commit = None
        db.commit()

    init_database(client.app.state.testing_session.kw["bind"])

    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        version = db.get(ProjectVersion, run["version_id"])
        assert project is not None and project.repository_path is not None
        assert version is not None and version.git_commit is not None


def test_project_file_browser_lists_repository_and_generated_artifacts(client) -> None:
    run = _built_run(client, prompt="Build a lighting product catalog")
    response = client.get(
        f"/api/projects/{run['project_id']}/files",
        params={"run_id": run["run_id"]},
    )
    assert response.status_code == 200
    files = response.json()
    assert any(item["source"] == "repository" and item["path"] == "README.md" for item in files)
    assert any(item["source"] == "repository" and item["path"] == "app-spec.json" for item in files)
    artifact_file = next(
        item
        for item in files
        if item["source"] == "artifact" and item["path"].endswith("app-spec.json")
    )
    content = client.get(
        f"/api/projects/{run['project_id']}/files/content",
        params={
            "run_id": run["run_id"],
            "path": artifact_file["path"],
            "source": "artifact",
        },
    )
    assert content.status_code == 200
    assert '"project_name"' in content.json()["content"]
    readme = next(
        item
        for item in files
        if item["source"] == "repository" and item["path"] == "README.md"
    )
    assert readme["kind"] == "markdown"
    assert readme["editable"] is True
    assert readme["render_mode"] == "markdown"
    assert artifact_file["editable"] is False


def test_project_document_save_uses_hash_git_and_idempotent_operation(client) -> None:
    run = _built_run(client)
    project_id = run["project_id"]
    versions_before = client.get(f"/api/projects/{project_id}/versions").json()
    opened = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    )
    assert opened.status_code == 200, opened.text
    baseline = opened.json()
    assert baseline["editable"] is True
    assert baseline["content_hash"].startswith("sha256:")
    updated = baseline["content"] + "\n## Notes\n\nSaved from the file panel.\n"
    operation_id = str(uuid4())
    payload = {
        "path": "README.md",
        "content": updated,
        "expected_content_hash": baseline["content_hash"],
        "operation_id": operation_id,
    }
    saved = client.put(f"/api/projects/{project_id}/files/content", json=payload)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result["git_commit"]
    assert result["version"] is None
    assert result["content_hash"] != baseline["content_hash"]

    replay = client.put(f"/api/projects/{project_id}/files/content", json=payload)
    assert replay.status_code == 200
    assert replay.json()["git_commit"] == result["git_commit"]
    assert client.get(f"/api/projects/{project_id}/versions").json() == versions_before
    assert client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    ).json()["content"] == updated

    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        operation = db.get(FileSaveOperation, operation_id)
        event = db.query(RunEvent).filter_by(event_type="project.file.updated").one()
        assert project is not None and project.active_write_run_id is None
        assert operation is not None and operation.status == "completed"
        assert event.payload["path"] == "README.md"
        operation.status = "writing"
        operation.target_hash = None
        project.active_write_run_id = operation.id
        db.commit()

    init_database(client.app.state.testing_session.kw["bind"])
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        operation = db.get(FileSaveOperation, operation_id)
        assert project is not None and project.active_write_run_id is None
        assert operation is not None and operation.status == "completed"
        assert operation.target_hash == result["content_hash"]


def test_project_document_save_rejects_stale_hash_and_keeps_latest_content(client) -> None:
    run = _built_run(client)
    project_id = run["project_id"]
    opened = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    ).json()
    first_content = opened["content"] + "\nFirst save.\n"
    first = client.put(
        f"/api/projects/{project_id}/files/content",
        json={
            "path": "README.md",
            "content": first_content,
            "expected_content_hash": opened["content_hash"],
            "operation_id": str(uuid4()),
        },
    )
    assert first.status_code == 200
    stale = client.put(
        f"/api/projects/{project_id}/files/content",
        json={
            "path": "README.md",
            "content": opened["content"] + "\nStale overwrite.\n",
            "expected_content_hash": opened["content_hash"],
            "operation_id": str(uuid4()),
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "REPOSITORY_FILE_CONFLICT"
    current = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    ).json()
    assert current["content"] == first_content


def test_file_panel_keeps_application_source_and_artifacts_read_only(client) -> None:
    run = _built_run(client)
    project_id = run["project_id"]
    source = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "app-spec.json", "source": "repository"},
    ).json()
    assert source["editable"] is False
    blocked = client.put(
        f"/api/projects/{project_id}/files/content",
        json={
            "path": "app-spec.json",
            "content": source["content"] + "\n// bypass validator\n",
            "expected_content_hash": source["content_hash"],
            "operation_id": str(uuid4()),
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "REPOSITORY_FILE_NOT_EDITABLE"


def test_project_document_save_respects_project_writer_and_owner(client) -> None:
    headers = {"X-User-ID": "document-owner"}
    run = _built_run(client, headers=headers)
    project_id = run["project_id"]
    opened = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
        headers=headers,
    ).json()
    payload = {
        "path": "README.md",
        "content": opened["content"] + "\nOwner edit.\n",
        "expected_content_hash": opened["content_hash"],
        "operation_id": str(uuid4()),
    }
    assert client.put(
        f"/api/projects/{project_id}/files/content",
        json=payload,
        headers={"X-User-ID": "other-user"},
    ).status_code == 404

    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        project.active_write_run_id = "active-agent-run"
        db.commit()
    busy = client.put(
        f"/api/projects/{project_id}/files/content",
        json={**payload, "operation_id": str(uuid4())},
        headers=headers,
    )
    assert busy.status_code == 409
    assert busy.json()["code"] == "PROJECT_WRITE_BUSY"
    current = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
        headers=headers,
    ).json()
    assert current["content"] == opened["content"]


def test_project_document_save_rolls_back_file_when_git_commit_fails(
    client, monkeypatch
) -> None:
    run = _built_run(client)
    project_id = run["project_id"]
    opened = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    ).json()
    original_git = repository_service._git

    def fail_commit(path, *arguments):
        if arguments and arguments[0] == "commit":
            raise repository_service.RepositoryError("simulated commit failure")
        return original_git(path, *arguments)

    monkeypatch.setattr(repository_service, "_git", fail_commit)
    failed = client.put(
        f"/api/projects/{project_id}/files/content",
        json={
            "path": "README.md",
            "content": opened["content"] + "\nThis must roll back.\n",
            "expected_content_hash": opened["content_hash"],
            "operation_id": str(uuid4()),
        },
    )
    assert failed.status_code == 500
    current = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": "README.md", "source": "repository"},
    ).json()
    assert current["content"] == opened["content"]
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None and project.active_write_run_id is None


def test_project_file_browser_blocks_cross_user_and_git_metadata(client) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a catalog", "mode": "team"},
        headers={"X-User-ID": "file-owner"},
    ).json()
    project_id = created["project_id"]
    assert client.get(
        f"/api/projects/{project_id}/files",
        headers={"X-User-ID": "other-user"},
    ).status_code == 404
    hidden = client.get(
        f"/api/projects/{project_id}/files/content",
        params={"path": ".git/config", "source": "repository"},
        headers={"X-User-ID": "file-owner"},
    )
    assert hidden.status_code == 404


def test_new_version_does_not_move_public_pointer_without_publish(client: TestClient) -> None:
    run = _built_run(client)
    published = client.post(
        f"/api/projects/{run['project_id']}/publish",
        json={"version_id": run["version_id"], "strategy": "always_latest"},
    ).json()
    client.post(
        f"/api/projects/{run['project_id']}/revisions",
        json={"hero_title": "Draft only until explicitly published"},
    )
    project = client.get(f"/api/projects/{run['project_id']}").json()
    assert project["current_version_id"] != run["version_id"]
    assert project["deployment"]["version_id"] == published["version_id"] == run["version_id"]


def test_vim_save_validates_and_creates_git_backed_version(client: TestClient) -> None:
    run = _built_run(client)
    original = AppSpec.model_validate(run["app_spec"])

    class FakeSandbox:
        closed: str | None = None

        def create(self, project_id: str) -> RemoteSandboxSession:
            return RemoteSandboxSession(
                session_id=f"remote-{project_id}",
                terminal_token="one-time-terminal-token",
                expires_at=now_utc() + timedelta(minutes=30),
            )

        def read_app_spec(self, _session_id: str) -> AppSpec:
            return original.model_copy(update={"hero_title": "Edited in restricted Vim"})

        def close(self, session_id: str) -> None:
            self.closed = session_id

    fake = FakeSandbox()
    client.app.dependency_overrides[get_sandbox] = lambda: lambda: fake
    try:
        opened = client.post(f"/api/projects/{run['project_id']}/sandbox/sessions")
        assert opened.status_code == 201, opened.text
        session = opened.json()
        saved = client.post(
            f"/api/projects/{run['project_id']}/sandbox/sessions/{session['session_id']}/save"
        )
    finally:
        client.app.dependency_overrides.pop(get_sandbox, None)
    assert saved.status_code == 200, saved.text
    assert saved.json()["app_spec"]["hero_title"] == "Edited in restricted Vim"
    assert saved.json()["git_commit"]
    assert fake.closed == f"remote-{run['project_id']}"


def test_concurrent_vim_save_claim_creates_only_one_version(client: TestClient) -> None:
    run = _built_run(client)
    original = AppSpec.model_validate(run["app_spec"])
    entered = Event()
    release = Event()

    class BlockingSandbox:
        def create(self, project_id: str) -> RemoteSandboxSession:
            return RemoteSandboxSession(
                session_id=f"remote-{project_id}",
                terminal_token="terminal-token",
                expires_at=now_utc() + timedelta(minutes=30),
            )

        def read_app_spec(self, _session_id: str) -> AppSpec:
            entered.set()
            assert release.wait(timeout=5)
            return original.model_copy(update={"hero_title": "One concurrent save"})

        def close(self, _session_id: str) -> None:
            return None

    fake = BlockingSandbox()
    client.app.dependency_overrides[get_sandbox] = lambda: lambda: fake
    try:
        opened = client.post(f"/api/projects/{run['project_id']}/sandbox/sessions").json()
        path = f"/api/projects/{run['project_id']}/sandbox/sessions/{opened['session_id']}/save"
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(client.post, path)
            assert entered.wait(timeout=5)
            second = pool.submit(client.post, path)
            second_response = second.result(timeout=5)
            release.set()
            first_response = first.result(timeout=5)
    finally:
        release.set()
        client.app.dependency_overrides.pop(get_sandbox, None)

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["code"] == "SANDBOX_SAVE_NOT_ALLOWED"
    versions = client.get(f"/api/projects/{run['project_id']}/versions").json()
    assert len(versions) == 2
