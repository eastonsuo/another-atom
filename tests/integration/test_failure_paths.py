from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.config import get_settings
from another_atom.storage.models import Approval, Artifact, User


def _create_run(
    client: TestClient,
    payload: dict,
    headers: dict | None = None,
    *,
    auto_approve: bool = True,
) -> dict:
    created = client.post("/api/runs", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}", headers=headers).json()
    if (
        auto_approve
        and run["status"] == "awaiting_approval"
        and run["blueprint"]["support_level"] == "supported"
    ):
        approved = client.post(
            f"/api/runs/{run_id}/approve",
            json={"blueprint": run["blueprint"]},
            headers=headers,
        )
        assert approved.status_code == 202, approved.text
        run = client.get(f"/api/runs/{run_id}", headers=headers).json()
    return run


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
    attempts = [event for event in events if event["type"] == "agent.attempt.started"]
    retries = [event for event in events if event["type"] == "agent.retry"]
    assert len(attempts) == 3
    assert [event["payload"]["attempt"] for event in attempts] == [1, 2, 3]
    assert len(retries) == 3
    assert [event["payload"]["will_retry"] for event in retries] == [True, True, False]
    assert all(event["payload"]["failure_kind"] == "provider_error" for event in retries)
    assert all(event["payload"]["failure_summary"] for event in retries)
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
    assert quota["used"] == 3
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
    assert ".another-atom/generated/engineer-output-repair.json" in paths
    assert ".another-atom/generated/repair-validation-report.json" in paths

    quota = client.get("/api/quota").json()
    assert quota["used"] == 4
    assert quota["reserved"] == 0


def test_runtime_unit_test_failure_is_repaired_with_revised_tests(
    client: TestClient,
) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a product catalog [repair:unit-tests]", "mode": "team"},
    )

    assert run["status"] == "completed"
    assert run["validation_report"]["passed"] is True
    repaired_tests = [
        item
        for item in run["source_bundle"]["files"]
        if item["role"] == "test"
    ]
    assert repaired_tests
    assert all("assert.equal(1, 2)" not in item["content"] for item in repaired_tests)

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    repair_event = next(event for event in events if event["type"] == "repair.completed")
    assert repair_event["payload"]["test_files"] == ["tests/app.test.js"]


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
    assert quota["used"] == 4
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


def test_supported_request_waits_for_product_spec_approval(client: TestClient) -> None:
    run = _create_run(
        client,
        {"prompt": "Build a product catalog", "mode": "team"},
        auto_approve=False,
    )
    assert run["status"] == "awaiting_approval"
    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    event_types = [event["type"] for event in events]
    assert "approval.required" in event_types
    approved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    assert approved.status_code == 202
    assert client.get(f"/api/runs/{run['run_id']}").json()["status"] == "completed"


def test_reviewer_marker_does_not_reenable_skipped_role(client: TestClient) -> None:
    run = _create_run(
        client,
        {
            "prompt": "Build a product catalog for lamps [review:rework]",
            "mode": "team",
        },
    )

    assert run["status"] == "completed"
    assert run["review_report"] is None
    assert run["version_id"] is not None


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
    assert "翻译软件" in run["product_spec"]["summary"]
    assert run["blueprint"]["modules"][0] in run["product_spec"]["summary"]
    assert "## 用户目标" in run["product_spec"]["content"]
    assert "创建一个带登录和数据库保存记录的翻译软件" in run["product_spec"]["content"]


def test_local_model_request_exposes_localhost_as_an_approval_gap(
    queued_client: TestClient,
) -> None:
    run = _create_run(
        queued_client,
        {
            "prompt": "创建一个可以调用本地大模型的翻译软件",
            "mode": "team",
            "model": "mock",
        },
    )

    assert run["status"] == "awaiting_approval"
    assert run["blueprint"]["support_level"] == "adapted"
    assert any(
        "localhost" in requirement
        for requirement in run["blueprint"]["omitted_requirements"]
    )
    assert all(
        "本地大模型" not in requirement
        for requirement in run["blueprint"]["mapped_requirements"]
    )
    assert "localhost" in run["product_spec"]["content"]
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

    updated = queued_client.post(
        f"/api/runs/{run['run_id']}/product-spec",
        json={"summary": "保留当前方案，但突出翻译结果复制", "action": "regenerate"},
    )
    assert updated.status_code == 200
    regenerated = updated.json()
    assert regenerated["blueprint"]["modules"][0] in regenerated["product_spec"]["summary"]
    assert regenerated["product_spec"]["content_hash"] != run["product_spec"]["content_hash"]
    messages = queued_client.get(
        f"/api/projects/{run['project_id']}/messages"
    ).json()
    assert any(
        message["role"] == "user"
        and message["content"] == "将当前方案摘要修改为：保留当前方案，但突出翻译结果复制"
        for message in messages
    )


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
