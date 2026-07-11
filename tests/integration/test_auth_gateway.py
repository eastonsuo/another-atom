from fastapi.testclient import TestClient

from another_atom.config import get_settings


def test_signup_session_and_logout_enforce_identity(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        unauthenticated = client.get("/api/projects")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "AUTHENTICATION_REQUIRED"

        signup = client.post(
            "/api/auth/signup",
            json={
                "username": "alice",
                "password": "correct-horse-battery-staple",
                "display_name": "Alice",
            },
        )
        assert signup.status_code == 201
        assert signup.json()["username"] == "alice"
        assert "another_atom_session=" in signup.headers["set-cookie"]
        assert "HttpOnly" in signup.headers["set-cookie"]
        assert client.get("/api/auth/me").json()["display_name"] == "Alice"

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/projects").status_code == 401
    finally:
        get_settings.cache_clear()


def test_two_authenticated_users_cannot_read_each_others_projects(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        client.post(
            "/api/auth/signup",
            json={"username": "alice2", "password": "correct-horse-battery-staple"},
        )
        created = client.post(
            "/api/runs",
            json={"prompt": "Build a product catalog", "mode": "team"},
        ).json()
        client.post("/api/auth/logout")
        client.post(
            "/api/auth/signup",
            json={"username": "bob2", "password": "another-correct-long-password"},
        )
        assert client.get(f"/api/projects/{created['project_id']}").status_code == 404
        assert client.get(f"/api/runs/{created['run_id']}").status_code == 404
    finally:
        get_settings.cache_clear()
