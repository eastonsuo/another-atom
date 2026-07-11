from fastapi.testclient import TestClient


def test_user_can_download_own_run_log(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a product catalog for home objects", "mode": "team"},
    ).json()

    response = client.get(f"/api/runs/{created['run_id']}/logs/download")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert f'filename="another-atom-run-{created["run_id"]}.log"' in response.headers[
        "content-disposition"
    ]
    assert f"Run ID: {created['run_id']}" in response.text
    assert "Events (" in response.text
    assert " stage.started" in response.text


def test_user_cannot_download_another_users_run_log(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    from another_atom.config import get_settings

    get_settings.cache_clear()
    try:
        client.post(
            "/api/auth/signup",
            json={"username": "log-owner", "password": "correct-horse-battery-staple"},
        )
        created = client.post(
            "/api/runs",
            json={"prompt": "Build a product catalog", "mode": "team"},
        ).json()
        client.post("/api/auth/logout")
        client.post(
            "/api/auth/signup",
            json={"username": "log-reader", "password": "another-correct-long-password"},
        )

        response = client.get(f"/api/runs/{created['run_id']}/logs/download")

        assert response.status_code == 404
    finally:
        get_settings.cache_clear()
