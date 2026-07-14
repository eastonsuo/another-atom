from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.config import get_settings
from another_atom.domain.auth import hash_password, verify_password
from another_atom.storage.database import create_database_engine, init_database
from another_atom.storage.models import Project, ProjectSession, Run, User


def _create_admin(client: TestClient) -> None:
    with client.app.state.testing_session() as db:
        db.add(
            User(
                username="admin",
                password_hash=hash_password("admin12345"),
                display_name="Another Atom Admin",
                role="admin",
                plan="internal",
                quota_limit=0,
            )
        )
        db.commit()


def test_database_bootstrap_creates_default_admin(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    get_settings.cache_clear()
    engine = create_database_engine(f"sqlite:///{tmp_path / 'bootstrap.db'}")
    try:
        init_database(engine)
        with Session(engine) as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            assert admin is not None
            assert admin.role == "admin"
            assert admin.password_hash is not None
            assert verify_password("admin12345", admin.password_hash)
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_database_bootstrap_preserves_console_assigned_admin_accounts(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    get_settings.cache_clear()
    engine = create_database_engine(f"sqlite:///{tmp_path / 'demote.db'}")
    try:
        init_database(engine)
        monkeypatch.setenv("ADMIN_USERNAME", "ops-admin")
        monkeypatch.setenv("ADMIN_PASSWORD", "ops-admin-password")
        get_settings.cache_clear()
        init_database(engine)
        with Session(engine) as db:
            stale = db.scalar(select(User).where(User.username == "admin"))
            assert stale is not None
            assert stale.role == "admin"
            configured = db.scalar(select(User).where(User.username == "ops-admin"))
            assert configured is not None
            assert configured.role == "admin"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_admin_login_locks_after_repeated_failures(
    client: TestClient, monkeypatch
) -> None:
    warning = Mock()
    monkeypatch.setattr("another_atom.api.admin_routes.logger.warning", warning)
    for _ in range(5):
        rejected = client.post(
            "/api/admin/login",
            json={"username": "brute-force-target", "password": "wrong-password"},
        )
        assert rejected.status_code == 401
    locked = client.post(
        "/api/admin/login",
        json={"username": "brute-force-target", "password": "wrong-password"},
    )
    assert locked.status_code == 429
    assert locked.json()["code"] == "ADMIN_LOGIN_LOCKED"
    assert warning.call_count == 5
    warning.assert_any_call(
        "admin_login_failed",
        extra={"resource_id": "brute-force-target", "status": "invalid_credentials"},
    )


def test_production_bootstrap_warns_for_demo_admin_and_insecure_cookie(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    warning = Mock()
    monkeypatch.setattr(
        "another_atom.observability.get_logger",
        lambda _name: Mock(warning=warning),
    )
    engine = create_database_engine(f"sqlite:///{tmp_path / 'production.db'}")
    try:
        init_database(engine)
        messages = [call.args[0] for call in warning.call_args_list]
        assert "default_admin_credentials_active" in messages
        assert "session_cookie_secure_disabled" in messages
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_admin_user_search_escapes_like_wildcards(client: TestClient) -> None:
    client.post(
        "/api/auth/signup",
        json={"username": "wildcard-user", "password": "wildcard-user-password"},
    )
    client.post("/api/auth/logout")
    _create_admin(client)
    client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    )
    assert client.get("/api/admin/users", params={"query": "%"}).json()["total"] == 0
    assert client.get("/api/admin/users", params={"query": "wildcard"}).json()["total"] == 1


def test_admin_endpoints_require_an_authenticated_admin(client: TestClient) -> None:
    unauthenticated = client.get("/api/admin/users")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"
    unauthenticated_update = client.patch(
        "/api/admin/users/missing/role", json={"role": "admin"}
    )
    assert unauthenticated_update.status_code == 401

    client.post(
        "/api/auth/signup",
        json={"username": "normal-user", "password": "normal-user-password"},
    )
    forbidden = client.get("/api/admin/users")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ADMIN_ACCESS_REQUIRED"
    forbidden_update = client.patch(
        "/api/admin/users/missing/role", json={"role": "admin"}
    )
    assert forbidden_update.status_code == 403

    admin_login = client.post(
        "/api/admin/login",
        json={"username": "normal-user", "password": "normal-user-password"},
    )
    assert admin_login.status_code == 403
    assert admin_login.json()["code"] == "ADMIN_ACCESS_REQUIRED"


def test_admin_can_promote_a_registered_user_and_the_role_survives_bootstrap(
    client: TestClient,
) -> None:
    created_user = client.post(
        "/api/auth/signup",
        json={
            "username": "future-admin",
            "password": "future-admin-password",
            "display_name": "Future Admin",
        },
    ).json()
    client.post("/api/auth/logout")
    _create_admin(client)
    assert client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    ).status_code == 200

    promoted = client.patch(
        f"/api/admin/users/{created_user['id']}/role",
        json={"role": "admin"},
    )

    assert promoted.status_code == 200
    assert promoted.headers["cache-control"] == "no-store"
    assert promoted.json() == {
        "id": created_user["id"],
        "username": "future-admin",
        "display_name": "Future Admin",
        "role": "admin",
    }
    assert client.get("/api/admin/users").json()["total"] == 0

    client.post("/api/auth/logout")
    promoted_login = client.post(
        "/api/admin/login",
        json={"username": "future-admin", "password": "future-admin-password"},
    )
    assert promoted_login.status_code == 200

    with client.app.state.testing_session() as db:
        engine = db.get_bind()
    init_database(engine)
    with client.app.state.testing_session() as db:
        persisted = db.get(User, created_user["id"])
        assert persisted is not None
        assert persisted.role == "admin"


def test_admin_role_update_rejects_invalid_or_missing_targets(client: TestClient) -> None:
    _create_admin(client)
    assert client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    ).status_code == 200

    invalid = client.patch("/api/admin/users/missing/role", json={"role": "user"})
    assert invalid.status_code == 422
    missing = client.patch("/api/admin/users/missing/role", json={"role": "admin"})
    assert missing.status_code == 404
    assert missing.json()["code"] == "USER_NOT_FOUND"


def test_admin_can_list_users_projects_and_latest_run(client: TestClient) -> None:
    created_user = client.post(
        "/api/auth/signup",
        json={
            "username": "project-owner",
            "password": "project-owner-password",
            "display_name": "Project Owner",
        },
    ).json()
    created_run = client.post(
        "/api/runs",
        json={"prompt": "Build a home objects catalog", "mode": "team"},
    ).json()
    client.post("/api/auth/logout")
    _create_admin(client)

    login = client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert client.get("/api/auth/me").json()["role"] == "admin"

    users = client.get("/api/admin/users")
    assert users.status_code == 200
    assert users.headers["cache-control"] == "no-store"
    payload = users.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == created_user["id"]
    assert payload["items"][0]["display_name"] == "Project Owner"
    assert payload["items"][0]["project_count"] == 1
    assert all(item["username"] != "admin" for item in payload["items"])

    projects = client.get(f"/api/admin/users/{created_user['id']}/projects")
    assert projects.status_code == 200
    assert projects.json()["total"] == 1
    project = projects.json()["items"][0]
    assert project["id"] == created_run["project_id"]
    assert project["summary"]
    assert project["latest_run"]["id"] == created_run["run_id"]
    assert project["latest_run"]["status"] in {"completed", "completed_degraded"}
    assert project["latest_run"]["current_stage"] == "complete"

    detail = client.get(f"/api/admin/projects/{created_run['project_id']}")
    assert detail.status_code == 200
    assert detail.json()["events"]
    assert detail.json()["project"]["latest_run"]["id"] == created_run["run_id"]

    log = client.get(f"/api/admin/runs/{created_run['run_id']}/logs/download")
    assert log.status_code == 200
    assert f"Run ID: {created_run['run_id']}" in log.text
    assert log.headers["cache-control"] == "no-store"


def test_admin_user_search_and_missing_resources(client: TestClient) -> None:
    client.post(
        "/api/auth/signup",
        json={
            "username": "searchable-user",
            "password": "searchable-user-password",
            "display_name": "Unique Display Name",
        },
    )
    client.post("/api/auth/logout")
    _create_admin(client)
    client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    )

    found = client.get("/api/admin/users", params={"query": "unique display"}).json()
    assert found["total"] == 1
    assert found["items"][0]["username"] == "searchable-user"
    assert client.get("/api/admin/users/missing/projects").status_code == 404
    assert client.get("/api/admin/projects/missing").status_code == 404
    assert client.get("/api/admin/runs/missing/logs/download").status_code == 404


def test_admin_project_list_is_paginated(client: TestClient) -> None:
    created_user = client.post(
        "/api/auth/signup",
        json={
            "username": "many-projects-user",
            "password": "many-projects-password",
            "display_name": "Many Projects",
        },
    ).json()
    with client.app.state.testing_session() as db:
        db.add_all(
            [
                Project(
                    user_id=created_user["id"],
                    name=f"Project {index}",
                    prompt=f"Prompt {index}",
                    mode="team",
                )
                for index in range(3)
            ]
        )
        db.commit()
    client.post("/api/auth/logout")
    _create_admin(client)
    assert client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    ).status_code == 200

    first = client.get(
        f"/api/admin/users/{created_user['id']}/projects",
        params={"page": 1, "page_size": 2},
    )
    second = client.get(
        f"/api/admin/users/{created_user['id']}/projects",
        params={"page": 2, "page_size": 2},
    )
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert first.json()["page"] == 1
    assert len(first.json()["items"]) == 2
    assert second.json()["page"] == 2
    assert len(second.json()["items"]) == 1
    assert client.get(
        f"/api/admin/users/{created_user['id']}/projects",
        params={"page_size": 101},
    ).status_code == 422


def test_admin_project_uses_latest_run_and_latest_available_blueprint(
    client: TestClient,
) -> None:
    created_user = client.post(
        "/api/auth/signup",
        json={
            "username": "blueprint-history-user",
            "password": "blueprint-history-password",
        },
    ).json()
    completed = client.post(
        "/api/runs",
        json={"prompt": "Build a home objects catalog", "mode": "team"},
    ).json()
    with client.app.state.testing_session() as db:
        session = ProjectSession(
            project_id=completed["project_id"],
            user_id=created_user["id"],
            title="Failed follow-up",
        )
        db.add(session)
        db.flush()
        failed = Run(
            project_id=completed["project_id"],
            session_id=session.id,
            user_id=created_user["id"],
            mode="team",
            model="mock",
            status="failed",
            current_stage="complete",
            prompt="Follow-up failed before producing a Blueprint",
            error_code="TEST_FAILURE",
            error_message="Synthetic failure for admin summary verification",
        )
        db.add(failed)
        db.commit()
        failed_id = failed.id
    client.post("/api/auth/logout")
    _create_admin(client)
    assert client.post(
        "/api/admin/login",
        json={"username": "admin", "password": "admin12345"},
    ).status_code == 200

    payload = client.get(
        f"/api/admin/users/{created_user['id']}/projects"
    ).json()["items"][0]
    assert payload["latest_run"]["id"] == failed_id
    assert payload["latest_run"]["status"] == "failed"
    assert payload["latest_run"]["current_stage"] == "complete"
    assert payload["support_level"] == "supported"
    assert payload["summary"] != "Build a home objects catalog"
