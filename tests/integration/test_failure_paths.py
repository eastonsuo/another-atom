from fastapi.testclient import TestClient

from another_atom.config import get_settings
from another_atom.storage.models import User


def _create_run(client: TestClient, payload: dict, headers: dict | None = None) -> dict:
    created = client.post("/api/runs", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    return client.get(f"/api/runs/{run_id}", headers=headers).json()


def test_unsupported_request_stops_before_approval(client: TestClient) -> None:
    run = _create_run(
        client, {"prompt": "Build a CRM for a sales organization", "mode": "team"}
    )
    assert run["status"] == "needs_input"
    assert run["blueprint"]["support_level"] == "unsupported"
    assert run["version_id"] is None


def test_llm_failure_retries_then_preserves_project(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a catalog [fail:llm]", "mode": "team"},
    )
    assert run["status"] == "failed"
    assert run["error_code"] == "LLM_OUTPUT_FAILED"

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert len([event for event in events if event["type"] == "agent.retry"]) == 3
    projects = client.get("/api/projects").json()
    assert any(project["id"] == run["project_id"] for project in projects)
    quota = client.get("/api/quota").json()
    assert quota["reserved"] == 0
    assert quota["used"] == 3


def test_non_llm_failure_releases_unsettled_quota(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a catalog [fail:platform]", "mode": "team"},
    )
    assert run["status"] == "failed"
    assert run["error_code"] == "BLUEPRINT_FAILED"
    quota = client.get("/api/quota").json()
    assert quota["reserved"] == 0
    assert quota["used"] == 1


def test_build_failure_has_no_false_progress_or_version(client: TestClient) -> None:
    created = _create_run(
        client, {"prompt": "Build a catalog [fail:build]", "mode": "team"}
    )
    approved = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": created["blueprint"]},
    )
    assert approved.status_code == 202
    run = client.get(f"/api/runs/{created['run_id']}").json()
    assert run["status"] == "failed"
    assert run["error_code"] == "BUILD_VALIDATION_FAILED"
    assert run["version_id"] is None
    assert client.get(f"/api/projects/{run['project_id']}/versions").json() == []


def test_blueprint_cannot_be_approved_twice(client: TestClient) -> None:
    created = _create_run(
        client, {"prompt": "Build a product catalog", "mode": "engineer"}
    )
    payload = {"blueprint": created["blueprint"]}
    assert client.post(f"/api/runs/{created['run_id']}/approve", json=payload).status_code == 202
    second = client.post(f"/api/runs/{created['run_id']}/approve", json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "APPROVAL_NOT_ALLOWED"


def test_cross_user_project_access_is_denied(client: TestClient) -> None:
    created = _create_run(
        client,
        {"prompt": "Build a product catalog", "mode": "team"},
        {"X-User-ID": "user-a"},
    )
    response = client.get(f"/api/projects/{created['project_id']}", headers={"X-User-ID": "user-b"})
    assert response.status_code == 404


def test_cross_user_preview_access_is_denied(client: TestClient) -> None:
    created = _create_run(
        client,
        {"prompt": "Build a product catalog", "mode": "team"},
        {"X-User-ID": "user-a"},
    )
    approved = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": created["blueprint"]},
        headers={"X-User-ID": "user-a"},
    ).json()
    response = client.get(
        f"/api/previews/{approved['version_id']}",
        headers={"X-User-ID": "user-b"},
    )
    assert response.status_code == 404


def test_unavailable_model_is_rejected_before_project_creation(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"prompt": "Build a product catalog", "mode": "team", "model": "unknown"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "MODEL_NOT_ALLOWED"


def test_unknown_user_is_not_created_outside_tests(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        response = client.get(
            "/api/quota",
            headers={"X-User-ID": "unknown-production-user"},
        )
        assert response.status_code == 401
        assert response.json()["code"] == "USER_NOT_FOUND"
        with client.app.state.testing_session() as db:
            assert db.get(User, "unknown-production-user") is None
    finally:
        get_settings.cache_clear()
