from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.config import get_settings
from another_atom.storage.models import Approval, Artifact, User


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


def test_build_usage_is_recorded_without_enforcing_the_configured_limit(
    client: TestClient,
) -> None:
    assert client.get("/api/quota").status_code == 200
    with client.app.state.testing_session() as db:
        user = db.get(User, "demo-user")
        assert user is not None
        user.quota_limit = 0
        db.commit()

    run = _create_run(client, {"prompt": "Build a catalog", "mode": "team"})

    assert run["status"] == "completed"
    quota = client.get("/api/quota").json()
    assert quota["limit"] == 0
    assert quota["used"] == 5
    assert quota["reserved"] == 0


def test_build_failure_has_no_false_progress_or_version(client: TestClient) -> None:
    run = _create_run(client, {"prompt": "Build a catalog [fail:build]", "mode": "team"})
    assert run["status"] == "failed"
    assert run["error_code"] == "BUILD_VALIDATION_FAILED"
    assert run["version_id"] is None
    assert client.get(f"/api/projects/{run['project_id']}/versions").json() == []
    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert "repair.started" not in [event["type"] for event in events]


def test_repairable_validation_failure_is_repaired_once(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a product catalog [repair:needed]", "mode": "team"},
    )

    assert run["status"] == "completed"
    assert run["app_spec"]["pages"][0]["route"] == "/"
    assert run["validation_report"]["passed"] is True
    assert run["version_id"]

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    event_types = [event["type"] for event in events]
    assert event_types.count("repair.started") == 1
    assert event_types.count("repair.completed") == 1
    assert event_types.count("repair.validation_completed") == 1

    files = client.get(
        f"/api/projects/{run['project_id']}/files",
        params={"run_id": run["run_id"]},
    ).json()
    paths = {entry["path"] for entry in files}
    assert ".another-atom/generated/app-spec.json" in paths
    assert ".another-atom/generated/validation-report.json" in paths
    assert ".another-atom/generated/app-spec-repair.json" in paths
    assert ".another-atom/generated/repair-validation-report.json" in paths

    quota = client.get("/api/quota").json()
    assert quota["used"] == 6
    assert quota["reserved"] == 0


def test_failed_repair_stops_after_one_round(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a product catalog [repair:still-fails]", "mode": "team"},
    )

    assert run["status"] == "failed"
    assert run["error_code"] == "BUILD_VALIDATION_FAILED"
    assert run["validation_report"]["passed"] is False
    assert run["version_id"] is None

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    event_types = [event["type"] for event in events]
    assert event_types.count("repair.started") == 1
    assert event_types.count("repair.completed") == 1
    assert event_types.count("repair.validation_completed") == 1
    assert "run.completed" not in event_types

    quota = client.get("/api/quota").json()
    assert quota["used"] == 5
    assert quota["reserved"] == 0


def test_blueprint_cannot_be_approved_twice(client: TestClient) -> None:
    created = _create_run(
        client,
        {"prompt": "Build a product catalog with login", "mode": "engineer"},
    )
    assert created["status"] == "awaiting_approval"
    assert created["blueprint"]["support_level"] == "adapted"
    payload = {"blueprint": created["blueprint"]}
    assert client.post(f"/api/runs/{created['run_id']}/approve", json=payload).status_code == 202
    with client.app.state.testing_session() as db:
        approval = db.scalar(select(Approval).where(Approval.run_id == created["run_id"]))
        assert approval is not None
        artifact = db.get(Artifact, approval.artifact_id)
        assert artifact is not None
        assert artifact.artifact_type == "product_spec"
        assert approval.payload["path"] == "docs/product-spec.md"
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


def test_chinese_adapted_request_creates_chinese_product_spec_for_review(
    queued_client: TestClient,
) -> None:
    run = _create_run(
        queued_client,
        {
            "prompt": "创建一个带登录和数据库保存记录的翻译软件",
            "mode": "team",
        },
    )

    assert run["status"] == "awaiting_approval"
    assert run["product_spec"]["path"] == "docs/product-spec.md"
    assert "## 用户目标" in run["product_spec"]["content"]
    assert "创建一个带登录和数据库保存记录的翻译软件" in run["product_spec"]["content"]
    assert "视觉方向" not in run["product_spec"]["content"]
    assert any("\u3400" <= character <= "\u9fff" for character in run["blueprint"]["modules"][0])
    assert run["pending_human_task"]["payload"]["artifact_type"] == "product_spec"
    assert run["pending_human_task"]["payload"]["path"] == "docs/product-spec.md"

    files = queued_client.get(
        f"/api/projects/{run['project_id']}/files",
        params={"run_id": run["run_id"]},
    ).json()
    assert any(
        item["source"] == "repository" and item["path"] == "docs/product-spec.md"
        for item in files
    )
    document = queued_client.get(
        f"/api/projects/{run['project_id']}/files/content",
        params={
            "run_id": run["run_id"],
            "source": "repository",
            "path": "docs/product-spec.md",
        },
    )
    assert document.status_code == 200
    assert document.json()["content"] == run["product_spec"]["content"]


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
