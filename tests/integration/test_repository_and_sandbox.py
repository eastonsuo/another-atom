import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

from fastapi.testclient import TestClient

from another_atom.api.dependencies import get_sandbox
from another_atom.contracts.schemas import AppSpec
from another_atom.sandbox.client import RemoteSandboxSession
from another_atom.storage.database import init_database
from another_atom.storage.models import Project, ProjectVersion, now_utc


def _built_run(client: TestClient, headers: dict | None = None) -> dict:
    initial = client.post(
        "/api/runs",
        json={"prompt": "Build a product catalog", "mode": "team"},
        headers=headers,
    ).json()
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
