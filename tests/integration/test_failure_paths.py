from fastapi.testclient import TestClient


def test_unsupported_request_stops_before_approval(client: TestClient) -> None:
    response = client.post(
        "/api/runs", json={"prompt": "Build a CRM for a sales organization", "mode": "team"}
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "needs_input"
    assert run["blueprint"]["support_level"] == "unsupported"
    assert run["version_id"] is None


def test_llm_failure_retries_then_preserves_project(client: TestClient) -> None:
    response = client.post(
        "/api/runs",
        json={"prompt": "Build a catalog [fail:llm]", "mode": "team"},
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "failed"
    assert run["error_code"] == "LLM_OUTPUT_FAILED"

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert len([event for event in events if event["type"] == "agent.retry"]) == 3
    projects = client.get("/api/projects").json()
    assert any(project["id"] == run["project_id"] for project in projects)
    quota = client.get("/api/quota").json()
    assert quota["reserved"] == 0


def test_build_failure_has_no_false_progress_or_version(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a catalog [fail:build]", "mode": "team"},
    ).json()
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
    created = client.post(
        "/api/runs", json={"prompt": "Build a product catalog", "mode": "engineer"}
    ).json()
    payload = {"blueprint": created["blueprint"]}
    assert client.post(f"/api/runs/{created['run_id']}/approve", json=payload).status_code == 202
    second = client.post(f"/api/runs/{created['run_id']}/approve", json=payload)
    assert second.status_code == 409
    assert second.json()["code"] == "APPROVAL_NOT_ALLOWED"


def test_cross_user_project_access_is_denied(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a product catalog", "mode": "team"},
        headers={"X-User-ID": "user-a"},
    ).json()
    response = client.get(f"/api/projects/{created['project_id']}", headers={"X-User-ID": "user-b"})
    assert response.status_code == 404
