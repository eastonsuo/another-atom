from fastapi.testclient import TestClient

from another_atom.config import get_settings
from another_atom.storage.models import User


def _create_run(client: TestClient, payload: dict, headers: dict | None = None) -> dict:
    created = client.post("/api/runs", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    return client.get(f"/api/runs/{run_id}", headers=headers).json()


def test_unsupported_request_stops_before_approval(client: TestClient) -> None:
    run = _create_run(client, {"prompt": "Build a native iOS camera app", "mode": "team"})
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
    run = _create_run(client, {"prompt": "Build a catalog [fail:build]", "mode": "team"})
    assert run["status"] == "failed"
    assert run["error_code"] == "BUILD_VALIDATION_FAILED"
    assert run["version_id"] is None
    assert client.get(f"/api/projects/{run['project_id']}/versions").json() == []


def test_blueprint_cannot_be_approved_twice(client: TestClient) -> None:
    created = _create_run(
        client,
        {"prompt": "Build a product catalog with login", "mode": "engineer"},
    )
    assert created["status"] == "awaiting_approval"
    assert created["blueprint"]["support_level"] == "adapted"
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
    response = client.get(
        f"/api/previews/{created['version_id']}",
        headers={"X-User-ID": "user-b"},
    )
    assert response.status_code == 404


def test_supported_request_auto_authorizes_build(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a product catalog", "mode": "team"},
    )
    assert run["status"] == "completed"
    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    event_types = [event["type"] for event in events]
    assert "build.auto_authorized" in event_types
    assert "approval.required" not in event_types


def test_reviewer_rework_blocks_version_and_preserves_report(client: TestClient) -> None:
    run = _create_run(
        client,
        {
            "prompt": "Build a product catalog for lamps [review:rework]",
            "mode": "team",
        },
    )

    assert run["status"] == "failed"
    assert run["error_code"] == "REVIEW_REJECTED"
    assert run["review_report"]["verdict"] == "rework"
    assert run["review_report"]["issues"][0]["severity"] == "blocker"
    assert run["version_id"] is None


def test_adapted_request_waits_for_approval(queued_client: TestClient) -> None:
    run = _create_run(
        queued_client,
        {"prompt": "Build a product catalog with login", "mode": "team"},
    )
    assert run["status"] == "awaiting_approval"
    assert run["blueprint"]["support_level"] == "adapted"
    assert run["build_job_id"] is None
    events = queued_client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert "approval.required" in [event["type"] for event in events]


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
        assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
        with client.app.state.testing_session() as db:
            assert db.get(User, "unknown-production-user") is None
    finally:
        get_settings.cache_clear()
