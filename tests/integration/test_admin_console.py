from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.config import get_settings
from another_atom.domain.auth import hash_password, verify_password
from another_atom.storage.database import create_database_engine, init_database
from another_atom.storage.models import User


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


def test_admin_endpoints_require_an_authenticated_admin(client: TestClient) -> None:
    unauthenticated = client.get("/api/admin/users")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"

    client.post(
        "/api/auth/signup",
        json={"username": "normal-user", "password": "normal-user-password"},
    )
    forbidden = client.get("/api/admin/users")
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ADMIN_ACCESS_REQUIRED"

    admin_login = client.post(
        "/api/admin/login",
        json={"username": "normal-user", "password": "normal-user-password"},
    )
    assert admin_login.status_code == 403
    assert admin_login.json()["code"] == "ADMIN_ACCESS_REQUIRED"


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
    project = projects.json()[0]
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
