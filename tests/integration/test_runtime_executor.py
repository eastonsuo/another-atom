import hashlib
import json
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    Blueprint,
    EngineerOutput,
    ExecutionRequest,
    SourceBundle,
    SourceFile,
    SourceFileDraft,
)
from another_atom.executor.app import app as executor_app
from another_atom.executor.runner import execute
from another_atom.runtime.artifacts import create_source_bundle
from another_atom.runtime.contracts import source_manifest_hash
from another_atom.storage.models import ProjectVersion


def _approve(client: TestClient, prompt: str) -> dict:
    response = client.post(
        "/api/runs",
        json={"prompt": prompt, "mode": "team"},
    )
    created = client.get(f"/api/runs/{response.json()['run_id']}").json()
    assert created["status"] == "awaiting_approval"
    approved = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": created["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    return client.get(f"/api/runs/{created['run_id']}").json()


def _execution_request(
    run: dict,
    execution_id: str,
    *,
    deadline_ms: int = 60_000,
    source_bundle: dict | None = None,
) -> ExecutionRequest:
    bundle = source_bundle or run["source_bundle"]
    request_payload = {
        "execution_id": execution_id,
        "run_id": run["run_id"],
        "attempt": 1,
        "adapter_id": bundle["adapter_id"],
        "runtime_binding": bundle.get("runtime_binding"),
        "product_spec_hash": run["product_spec"]["content_hash"],
        "architecture_design_hash": run["architecture_design"]["content_hash"],
        "source_manifest_hash": bundle["manifest_hash"],
        "prompt": run["prompt"],
        "blueprint": run["blueprint"],
        "architecture_design": run["architecture_design"],
        "app_spec": run["app_spec"],
        "source_bundle": bundle,
        "acceptance_criteria": run["architecture_design"]["acceptance_mapping"],
        "deadline_ms": deadline_ms,
    }
    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ExecutionRequest(**request_payload, request_hash=request_hash)


def test_approved_build_produces_architecture_source_tests_and_execution_evidence(
    client: TestClient,
) -> None:
    run = _approve(client, "Build a minimalist lighting catalog")

    assert run["status"] == "completed"
    assert run["source_bundle"]["schema_version"] == "2.0"
    assert run["source_bundle"]["runtime_binding"]["contract_id"] == "web-static-document"
    assert run["app_spec"]["html"] == ""
    index_source = next(
        item["content"] for item in run["source_bundle"]["files"] if item["path"] == "index.html"
    )
    assert "<!doctype html>" in index_source.casefold()
    assert run["architecture_design"]["path"] == "docs/architecture-design.md"
    assert run["architecture_design"]["requires_product_reapproval"] is False
    assert "架构设计文档" in run["architecture_design"]["content"]
    assert any(
        item["path"] == "tests/app.test.js" and item["role"] == "test"
        for item in run["source_bundle"]["files"]
    )
    assert run["execution_report"]["status"] == "passed"
    assert run["execution_report"]["build"]["status"] == "passed"
    assert run["execution_report"]["test"]["status"] == "passed"
    assert run["execution_report"]["tests_collected"] == 1
    assert run["data_profile"] is None
    assert run["review_report"] is None

    files = client.get(f"/api/projects/{run['project_id']}/files").json()
    paths = {item["path"] for item in files}
    assert "docs/architecture-design.md" in paths
    assert "tests/app.test.js" in paths

    with client.app.state.testing_session() as db:
        version = db.scalar(select(ProjectVersion).where(ProjectVersion.id == run["version_id"]))
        assert version is not None
        assert version.architecture_design is not None
        assert version.source_bundle is not None
        assert version.execution_report["status"] == "passed"
    assert version.build_artifact["files"]


def test_non_web_project_is_delivered_as_source_ready_without_fake_preview(
    client: TestClient,
) -> None:
    run = _approve(client, "构建一个命令行工具，用来整理文本文件")

    assert run["status"] == "completed_degraded"
    assert run["source_bundle"]["schema_version"] == "2.0"
    assert run["source_bundle"]["runtime_binding"] is None
    assert all(item["path"] != "index.html" for item in run["source_bundle"]["files"])
    assert run["execution_report"] is None

    versions = client.get(f"/api/projects/{run['project_id']}/versions")
    assert versions.status_code == 200
    version = versions.json()[0]
    assert version["delivery_outcome"] == "source_ready"
    assert version["runtime_capabilities"] == {
        "build": False,
        "test": False,
        "preview": False,
        "publish": False,
    }
    preview = client.get(f"/api/previews/{version['id']}")
    assert preview.status_code == 409
    assert preview.json()["code"] == "PREVIEW_NOT_SUPPORTED"
    publish = client.post(
        f"/api/projects/{run['project_id']}/publish",
        json={"version_id": version["id"], "strategy": "specify_version"},
    )
    assert publish.status_code == 409
    assert publish.json()["code"] == "PUBLISH_NOT_SUPPORTED"


def test_architecture_only_returns_to_human_when_product_boundary_changes(
    client: TestClient,
) -> None:
    run = _approve(
        client,
        "Build a browser tool [architecture:scope-change]",
    )

    assert run["status"] == "needs_input"
    assert run["version_id"] is None
    assert run["architecture_design"]["requires_product_reapproval"] is True
    assert run["pending_human_task"]["kind"] == "input_request"
    assert "产品规格" in run["pending_human_task"]["prompt"]

    original_product_hash = run["product_spec"]["content_hash"]
    response = client.post(
        f"/api/human-tasks/{run['pending_human_task']['id']}/respond",
        json={"response": "保持浏览器目标，但删除架构师提出的新增外部能力。"},
    )
    assert response.status_code == 202, response.text
    revised = client.get(f"/api/runs/{run['run_id']}").json()
    assert revised["status"] == "awaiting_approval"
    assert revised["product_spec"]["content_hash"] != original_product_hash
    reapproved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": revised["blueprint"]},
    )
    assert reapproved.status_code == 202, reapproved.text


def test_executor_private_http_stream_authenticates_and_returns_terminal_result(
    client: TestClient,
) -> None:
    run = _approve(client, "Build a small browser timer")
    execution_request = _execution_request(run, "http-contract-test-1")
    body = json.dumps(execution_request.model_dump(mode="json"), ensure_ascii=False).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Authorization": f"Bearer {get_settings().runtime_executor_shared_token}",
        "X-Executor-Timestamp": timestamp,
        "X-Content-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
    }

    with TestClient(executor_app) as executor:
        denied = executor.post(
            "/v1/executions",
            content=body,
            headers={**headers, "Authorization": "Bearer invalid"},
        )
        assert denied.status_code == 401
        response = executor.post("/v1/executions", content=body, headers=headers)

    assert response.status_code == 200, response.text
    envelopes = [json.loads(line) for line in response.text.splitlines()]
    assert envelopes[0]["kind"] == "event"
    assert envelopes[0]["data"]["type"] == "execution.accepted"
    assert envelopes[-1]["kind"] == "result"
    assert envelopes[-1]["data"]["status"] == "passed"
    assert envelopes[-1]["data"]["execution_report"]["test"]["status"] == "passed"


def test_executor_rejects_disallowed_package_json_before_materializing_source(
    client: TestClient,
) -> None:
    run = _approve(client, "Build a small browser timer")
    bundle = SourceBundle.model_validate(run["source_bundle"])
    package_json = '{"type":"module"}\n'
    candidate = bundle.model_copy(
        update={
            "files": [
                *[item for item in bundle.files if item.path != "package.json"],
                SourceFile(
                    path="package.json",
                    role="config",
                    content=package_json,
                    content_hash=(
                        "sha256:" + hashlib.sha256(package_json.encode("utf-8")).hexdigest()
                    ),
                ),
            ]
        }
    )
    candidate = candidate.model_copy(
        update={"manifest_hash": source_manifest_hash(candidate)}
    )

    events, result = execute(
        _execution_request(
            run,
            "manifest-preflight-test",
            source_bundle=candidate.model_dump(mode="json"),
        )
    )

    assert result.status == "failed"
    assert result.execution_report.error_code == "RUNTIME_PREFLIGHT_REJECTED"
    assert result.execution_report.build.status == "not_run"
    assert result.execution_report.test.status == "not_run"
    assert all(event.type != "source.materializing" for event in events)


def test_executor_enforces_deadline_and_cancellation(client: TestClient) -> None:
    run = _approve(client, "Build a browser stopwatch")
    blueprint = Blueprint.model_validate(run["blueprint"])
    hanging_bundle = create_source_bundle(
        EngineerOutput(
            app_spec=AppSpec.model_validate(run["app_spec"]),
            unit_tests=[
                SourceFileDraft(
                    path="tests/deadline.test.js",
                    role="test",
                    content=(
                        "import test from 'node:test';\n"
                        "test('等待截止时间', async () => {\n"
                        "  setInterval(() => {}, 1000);\n"
                        "  await new Promise(() => {});\n"
                        "});\n"
                    ),
                )
            ],
        ),
        blueprint.product_type,
    )
    _, timed_out = execute(
        _execution_request(
            run,
            "deadline-contract-test",
            deadline_ms=1_000,
            source_bundle=hanging_bundle.model_dump(mode="json"),
        )
    )
    assert timed_out.status == "failed"
    assert timed_out.execution_report.error_code == "EXECUTION_TIMEOUT"
    assert timed_out.execution_report.test.status == "timeout"

    cancellation = threading.Event()
    cancellation.set()
    _, cancelled = execute(
        _execution_request(run, "cancellation-contract-test"),
        cancel_event=cancellation,
    )
    assert cancelled.status == "cancelled"
    assert cancelled.execution_report.error_code == "EXECUTION_CANCELLED"
