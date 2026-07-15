import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from another_atom.agent.provider import MockLLMProvider
from another_atom.build.worker import process_next_job
from another_atom.storage.models import (
    Artifact,
    BuildJob,
    Project,
    ProjectVersion,
    Run,
    RunEvent,
)


def _build_project(client: TestClient) -> dict:
    created = client.post(
        "/api/runs",
        json={
            "prompt": "创建一个复古像素风扫雷游戏，包含计时、插旗和重新开始",
            "mode": "team",
        },
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["run_id"]
    run = client.get(f"/api/runs/{run_id}")
    assert run.status_code == 200
    if run.json()["status"] == "awaiting_approval":
        approved = client.post(
            f"/api/runs/{run_id}/approve",
            json={"blueprint": run.json()["blueprint"]},
        )
        assert approved.status_code == 202, approved.text
        run = client.get(f"/api/runs/{run_id}")
    if run.json()["status"] == "build_queued":
        assert process_next_job(client.app.state.testing_session, worker_id="initial-worker")
        run = client.get(f"/api/runs/{run_id}")
    assert run.json()["status"] == "completed"
    return run.json()


def _project_write_counts(client: TestClient, project_id: str) -> tuple[int, int, int]:
    with client.app.state.testing_session() as db:
        run_count = db.scalar(select(func.count(Run.id)).where(Run.project_id == project_id))
        job_count = db.scalar(
            select(func.count(BuildJob.id)).where(BuildJob.project_id == project_id)
        )
        version_count = db.scalar(
            select(func.count(ProjectVersion.id)).where(ProjectVersion.project_id == project_id)
        )
    return int(run_count or 0), int(job_count or 0), int(version_count or 0)


def _propose_change(client: TestClient, project_id: str, message: str) -> dict:
    response = client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": message, "model": "mock"},
    )
    assert response.status_code == 200, response.text
    proposal = response.json()
    assert proposal["intent"] == "propose_change"
    assert proposal["proposal_id"] == proposal["lead_message"]["id"]
    assert proposal["user_message"]["run_id"] is None
    assert proposal["lead_message"]["run_id"] is None
    assert proposal["lead_message"]["message_type"] == "change_proposal"
    assert proposal["lead_message"]["payload"]["status"] == "pending"
    return proposal


def _approve_change(client: TestClient, project_id: str, proposal_id: str) -> dict:
    response = client.post(f"/api/projects/{project_id}/change-proposals/{proposal_id}/approve")
    assert response.status_code == 202, response.text
    return response.json()


def test_project_chat_proposes_then_modifies_existing_code(
    client: TestClient,
    monkeypatch,
) -> None:
    def reject_legacy_full_app_spec(*args, **kwargs):
        raise AssertionError("Project modification must not call revise_app_spec")

    monkeypatch.setattr(MockLLMProvider, "revise_app_spec", reject_legacy_full_app_spec)
    initial = _build_project(client)
    project_id = initial["project_id"]
    deployment = client.post(
        f"/api/projects/{project_id}/publish",
        json={"version_id": initial["version_id"], "strategy": "specify_version"},
    ).json()
    before = _project_write_counts(client, project_id)

    proposal = _propose_change(
        client,
        project_id,
        "把标题改成“夜间扫雷”，保留计时和插旗逻辑",
    )

    assert _project_write_counts(client, project_id) == before
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        assert project.active_write_run_id is None

    run = _approve_change(client, project_id, proposal["proposal_id"])
    assert run["status"] == "completed"
    assert run["trigger"] == "ai_edit"
    assert run["base_version_id"] == initial["version_id"]
    assert run["version_id"] != initial["version_id"]
    assert run["app_spec"]["hero_title"] == "夜间扫雷"
    changed_index = next(
        item["content"] for item in run["source_bundle"]["files"] if item["path"] == "index.html"
    )
    assert changed_index.casefold().startswith("<!doctype html>")
    assert "夜间扫雷" in changed_index
    counts_after_approval = _project_write_counts(client, project_id)
    duplicate = _approve_change(client, project_id, proposal["proposal_id"])
    assert duplicate["run_id"] == run["run_id"]
    assert _project_write_counts(client, project_id) == counts_after_approval

    versions = client.get(f"/api/projects/{project_id}/versions").json()
    assert [(version["number"], version["source"]) for version in versions] == [
        (2, "ai_edit"),
        (1, "build"),
    ]
    assert versions[0]["git_commit"] != versions[1]["git_commit"]

    messages = client.get(f"/api/projects/{project_id}/messages").json()
    assert [(message["role"], message["message_type"]) for message in messages] == [
        ("user", "request"),
        ("user", "request"),
        ("lead", "change_proposal"),
        ("lead", "change_brief"),
        ("system", "result"),
    ]
    assert messages[1]["run_id"] == run["run_id"]
    assert messages[2]["run_id"] == run["run_id"]
    assert messages[2]["payload"]["status"] == "approved"
    assert messages[2]["payload"]["base_version_id"] == initial["version_id"]

    public_app = client.get(f"/api/public/{deployment['public_id']}").json()
    assert public_app["app_spec"]["hero_title"] != "夜间扫雷"
    with client.app.state.testing_session() as db:
        artifacts = set(
            db.scalars(select(Artifact.artifact_type).where(Artifact.run_id == run["run_id"])).all()
        )
        source_context = db.scalar(
            select(Artifact).where(
                Artifact.run_id == run["run_id"],
                Artifact.artifact_type == "source_context",
            )
        )
        architecture_design = db.scalar(
            select(Artifact).where(
                Artifact.run_id == run["run_id"],
                Artifact.artifact_type == "architecture_design",
            )
        )
    assert {
        "change_brief",
        "requirement_delta",
        "base_source_snapshot",
        "source_context",
        "source_file_change_set",
        "source_change_apply_report",
        "source_diff",
        "architecture_design",
        "architecture_spec",
        "app_spec",
        "source_bundle",
        "execution_report",
        "build_artifact",
        "validation_report",
    } <= artifacts
    assert source_context is not None
    assert architecture_design is not None
    assert any("夜间扫雷" in item for item in architecture_design.payload["interactions"])
    assert source_context.payload["trimming_applied"] is False
    assert {item["path"] for item in source_context.payload["included_files"]} == {
        "index.html",
        "styles.css",
        "app.js",
        "tests/app.test.js",
    }
    assert source_context.payload["runtime_managed_files"] == ["app-spec.json"]
    project_files = client.get(
        f"/api/projects/{project_id}/files", params={"run_id": run["run_id"]}
    ).json()
    project_paths = {entry["path"] for entry in project_files}
    assert ".another-atom/generated/source-file-change-set.json" in project_paths
    assert ".another-atom/generated/source-change-apply-report.json" in project_paths
    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    event_types = [event["type"] for event in events]
    assert "source.change_created" in event_types
    assert "source.change_check_started" in event_types
    assert "source.change_applied" in event_types
    assert "source.diff_created" in event_types


def test_source_only_project_change_patches_existing_source_without_fake_runtime(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "构建一个命令行工具，用来整理文本文件", "mode": "team"},
    ).json()
    initial = client.get(f"/api/runs/{created['run_id']}").json()
    approved = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": initial["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    initial = client.get(f"/api/runs/{created['run_id']}").json()
    assert initial["status"] == "completed_degraded"

    proposal = _propose_change(
        client,
        initial["project_id"],
        "增加一个按文件扩展名分组的选项",
    )
    changed = _approve_change(
        client,
        initial["project_id"],
        proposal["proposal_id"],
    )

    assert changed["status"] == "completed_degraded"
    assert changed["source_bundle"]["runtime_binding"] is None
    assert changed["execution_report"] is None
    assert all(item["path"] != "index.html" for item in changed["source_bundle"]["files"])
    assert any(
        "增加一个按文件扩展名分组的选项" in item["content"]
        for item in changed["source_bundle"]["files"]
        if item["role"] in {"source", "documentation"}
    )
    version = client.get(f"/api/projects/{initial['project_id']}/versions").json()[0]
    assert version["delivery_outcome"] == "source_ready"


def test_project_chat_clarifies_before_creating_a_run(client: TestClient) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    before = _project_write_counts(client, project_id)

    clarification = client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": "改一下 [pm:clarify]", "model": "mock"},
    )

    assert clarification.status_code == 200, clarification.text
    assert clarification.json()["intent"] == "clarify"
    assert clarification.json()["proposal_id"] is None
    assert clarification.json()["lead_message"]["message_type"] == "clarification"
    assert _project_write_counts(client, project_id) == before

    proposal = _propose_change(
        client,
        project_id,
        "把标题改成“澄清后的扫雷”，其他功能保持不变",
    )
    run = _approve_change(client, project_id, proposal["proposal_id"])
    assert run["status"] == "completed"
    assert run["app_spec"]["hero_title"] == "澄清后的扫雷"

    messages = client.get(f"/api/projects/{project_id}/messages").json()
    assert [(message["role"], message["message_type"]) for message in messages[-6:]] == [
        ("user", "request"),
        ("lead", "clarification"),
        ("user", "request"),
        ("lead", "change_proposal"),
        ("lead", "change_brief"),
        ("system", "result"),
    ]


def test_project_chat_answer_uses_context_without_creating_a_run(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    before = _project_write_counts(client, project_id)

    answered = client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": "这个项目使用了哪些颜色？", "model": "mock"},
    )

    assert answered.status_code == 200, answered.text
    result = answered.json()
    assert result["intent"] == "answer"
    assert result["proposal_id"] is None
    assert result["user_message"]["run_id"] is None
    assert result["lead_message"]["run_id"] is None
    assert initial["app_spec"]["primary_color"] in result["lead_message"]["content"]
    assert initial["app_spec"]["accent_color"] in result["lead_message"]["content"]
    assert initial["app_spec"]["background_color"] in result["lead_message"]["content"]
    assert _project_write_counts(client, project_id) == before

    context = result["lead_message"]["payload"]
    assert context["context_hash"].startswith("sha256:")
    assert context["document_contracts"] == [
        "product_spec",
        "blueprint",
        "architecture_spec",
        "application",
    ]
    assert context["conversation_message_count"] == 2
    assert context["trimming_applied"] is False
    assert {item["path"] for item in context["included_files"]} == {
        "app-spec.json",
        "index.html",
        "styles.css",
        "app.js",
        "tests/app.test.js",
    }
    versions = client.get(f"/api/projects/{project_id}/versions").json()
    assert [version["id"] for version in versions] == [initial["version_id"]]
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        assert project.active_write_run_id is None


def test_project_chat_stream_updates_the_same_persisted_lead_message(
    client: TestClient,
    monkeypatch,
) -> None:
    class StreamingProjectProvider(MockLLMProvider):
        def __init__(self) -> None:
            super().__init__()
            self.event_handler = None

        def begin_stage(self, *, timeout_seconds, event_handler=None) -> None:
            del timeout_seconds
            self.event_handler = event_handler

        def end_stage(self) -> None:
            self.event_handler = None

        def route_project_message(self, message, project_context, *, stream=False):
            decision = super().route_project_message(message, project_context, stream=stream)
            if stream and self.event_handler:
                encoded = json.dumps(
                    {"message": "正在读取项目上下文。", "result": decision.model_dump(mode="json")},
                    ensure_ascii=False,
                )
                midpoint = len(encoded) // 2
                self.event_handler(
                    "agent.message.delta",
                    {"delta": "正在读取项目上下文。"},
                )
                self.event_handler("agent.output.delta", {"delta": encoded[:midpoint]})
                self.event_handler("agent.output.delta", {"delta": encoded[midpoint:]})
                self.event_handler("agent.message.completed", {})
            return decision

    provider = StreamingProjectProvider()
    monkeypatch.setattr(
        "another_atom.api.routes.get_llm_provider",
        lambda model=None: provider,
    )
    initial = _build_project(client)
    response = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={
            "message": "这个项目使用了哪些颜色？",
            "model": "mock",
            "client_message_id": "optimistic-test-message",
        },
    )

    assert response.status_code == 200, response.text
    lead = response.json()["lead_message"]
    assert lead["message_type"] == "answer"
    assert lead["payload"]["status"] == "completed"
    assert lead["payload"]["model_output"].startswith('{"message": "正在读取项目上下文。"')
    messages = client.get(f"/api/projects/{initial['project_id']}/messages").json()
    turn_messages = [
        message
        for message in messages
        if message["payload"].get("client_message_id") == "optimistic-test-message"
        or message["id"] == lead["id"]
    ]
    assert [(message["role"], message["message_type"]) for message in turn_messages] == [
        ("user", "request"),
        ("lead", "answer"),
    ]


def test_failed_first_build_can_continue_with_a_new_approved_request(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/runs",
        json={
            "prompt": "创建一个扫雷游戏 [fail:engineer]",
            "mode": "team",
            "model": "mock",
        },
    )
    assert created.status_code == 201, created.text
    failed = client.get(f"/api/runs/{created.json()['run_id']}").json()
    approved = client.post(
        f"/api/runs/{failed['run_id']}/approve",
        json={"blueprint": failed["blueprint"]},
    )
    assert approved.status_code == 202
    failed = client.get(f"/api/runs/{failed['run_id']}").json()
    assert failed["status"] == "failed"
    assert failed["version_id"] is None
    before = _project_write_counts(client, failed["project_id"])

    proposal = _propose_change(
        client,
        failed["project_id"],
        "继续原项目：创建一个扫雷游戏，包含计时、插旗和重新开始",
    )
    assert _project_write_counts(client, failed["project_id"]) == before

    resumed = _approve_change(client, failed["project_id"], proposal["proposal_id"])
    assert resumed["project_id"] == failed["project_id"]
    assert resumed["run_id"] != failed["run_id"]
    resumed = client.get(f"/api/runs/{resumed['run_id']}").json()
    assert resumed["status"] == "awaiting_approval"
    approved = client.post(
        f"/api/runs/{resumed['run_id']}/approve",
        json={"blueprint": resumed["blueprint"]},
    )
    assert approved.status_code == 202
    resumed = client.get(f"/api/runs/{resumed['run_id']}").json()
    assert resumed["status"] == "completed"
    assert resumed["version_id"]

    projects = client.get("/api/projects").json()
    assert [project["id"] for project in projects] == [failed["project_id"]]
    with client.app.state.testing_session() as db:
        recovery_event = db.scalar(
            select(RunEvent).where(
                RunEvent.run_id == resumed["run_id"],
                RunEvent.event_type == "project.recovery_started",
            )
        )
    assert recovery_event is not None
    assert recovery_event.payload["retry_of_run_id"] == failed["run_id"]


def test_failed_run_retry_creates_new_run_without_change_proposal(
    client: TestClient,
) -> None:
    original = client.post(
        "/api/runs",
        json={
            "prompt": "创建一个带计时和历史记录的翻译工具",
            "mode": "team",
            "model": "mock",
        },
    ).json()
    with client.app.state.testing_session() as db:
        failed_run = db.get(Run, original["run_id"])
        project = db.get(Project, original["project_id"])
        assert failed_run is not None
        assert project is not None
        failed_run.status = "failed"
        failed_run.current_stage = "engineer"
        failed_run.error_code = "BUILD_VALIDATION_FAILED"
        failed_run.error_message = "Generated tests failed"
        project.status = "draft"
        project.active_write_run_id = None
        db.commit()

    before = _project_write_counts(client, original["project_id"])
    response = client.post(f"/api/runs/{original['run_id']}/retry")

    assert response.status_code == 202, response.text
    retried = response.json()
    assert retried["project_id"] == original["project_id"]
    assert retried["run_id"] != original["run_id"]
    assert retried["prompt"] == original["prompt"]
    assert retried["status"] == "product_running"
    retried = client.get(f"/api/runs/{retried['run_id']}").json()
    assert retried["status"] == "awaiting_approval"
    preserved_failure = client.get(f"/api/runs/{original['run_id']}").json()
    assert preserved_failure["status"] == "failed"
    assert preserved_failure["error_code"] == "BUILD_VALIDATION_FAILED"
    after = _project_write_counts(client, original["project_id"])
    assert after == (before[0] + 1, before[1], before[2])

    messages = client.get(f"/api/projects/{original['project_id']}/messages").json()
    retry_request = next(message for message in messages if message["run_id"] == retried["run_id"])
    assert retry_request["message_type"] == "request"
    assert retry_request["payload"]["request_type"] == "retry_build"
    assert retry_request["payload"]["retry_of_run_id"] == original["run_id"]
    assert all(message["message_type"] != "change_proposal" for message in messages)

    with client.app.state.testing_session() as db:
        recovery_event = db.scalar(
            select(RunEvent).where(
                RunEvent.run_id == retried["run_id"],
                RunEvent.event_type == "project.recovery_started",
            )
        )
    assert recovery_event is not None
    assert recovery_event.payload["retry_of_run_id"] == original["run_id"]


def test_retry_rejects_a_run_that_has_not_failed(client: TestClient) -> None:
    run = client.post(
        "/api/runs",
        json={"prompt": "创建一个翻译工具", "mode": "team", "model": "mock"},
    ).json()

    response = client.post(f"/api/runs/{run['run_id']}/retry")

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_RETRY_NOT_ALLOWED"


def test_pending_proposal_becomes_stale_when_base_version_changes(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    stale_proposal = _propose_change(client, project_id, "把标题改成新的标题")
    current_proposal = _propose_change(client, project_id, "把主色改成蓝色")
    current = _approve_change(client, project_id, current_proposal["proposal_id"])
    assert current["status"] == "completed"

    stale = client.post(
        f"/api/projects/{project_id}/change-proposals/{stale_proposal['proposal_id']}/approve"
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "BASE_VERSION_CHANGED"
    messages = client.get(f"/api/projects/{project_id}/messages").json()
    stale_message = next(
        message for message in messages if message["id"] == stale_proposal["proposal_id"]
    )
    assert stale_message["payload"]["status"] == "stale"


def test_project_blocks_new_chat_while_a_change_run_is_active(
    queued_client: TestClient,
) -> None:
    initial = _build_project(queued_client)
    project_id = initial["project_id"]
    first_proposal = _propose_change(queued_client, project_id, "把主色改成蓝色")
    first = _approve_change(queued_client, project_id, first_proposal["proposal_id"])
    assert first["status"] == "build_queued"

    second = queued_client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": "再修改标题", "model": "mock"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "PROJECT_CONVERSATION_BUSY"

    assert process_next_job(
        queued_client.app.state.testing_session,
        worker_id="change-worker",
    )
    completed = queued_client.get(f"/api/runs/{first['run_id']}").json()
    assert completed["status"] == "completed"
    with queued_client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        assert project.active_write_run_id is None

    next_message = _propose_change(queued_client, project_id, "再修改标题")
    assert next_message["intent"] == "propose_change"


def test_project_lead_turn_is_locked_across_requests_and_stale_lock_recovers(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        project.active_turn_id = "11111111-1111-4111-8111-111111111111"
        project.active_turn_started_at = datetime.now(UTC)
        db.commit()

    busy = client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": "这个项目有哪些页面？", "model": "mock"},
    )
    assert busy.status_code == 409
    assert busy.json()["code"] == "PROJECT_CONVERSATION_BUSY"

    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        project.active_turn_started_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()

    recovered = client.post(
        f"/api/projects/{project_id}/messages",
        json={"message": "这个项目有哪些页面？", "model": "mock"},
    )
    assert recovered.status_code == 200
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        assert project is not None
        assert project.active_turn_id is None
        assert project.active_turn_started_at is None


def test_failed_change_preserves_base_version_and_releases_project_lock(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    proposal = _propose_change(
        client,
        project_id,
        "修改标题 [fail:engineer-change]",
    )
    failed = _approve_change(client, project_id, proposal["proposal_id"])
    assert failed["status"] == "failed"
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        run = db.get(Run, failed["run_id"])
        versions = db.scalars(
            select(ProjectVersion).where(ProjectVersion.project_id == project_id)
        ).all()
        assert project is not None and run is not None
        assert project.latest_version_id == initial["version_id"]
        assert project.active_write_run_id is None
        assert len(versions) == 1
    messages = client.get(f"/api/projects/{project_id}/messages").json()
    assert messages[-1]["message_type"] == "error"

    continued_proposal = _propose_change(
        client,
        project_id,
        "继续，把标题改成“恢复后的扫雷”",
    )
    continued = _approve_change(client, project_id, continued_proposal["proposal_id"])
    assert continued["status"] == "completed"
    assert continued["base_version_id"] == initial["version_id"]
    with client.app.state.testing_session() as db:
        brief = db.scalar(
            select(Artifact).where(
                Artifact.run_id == continued["run_id"],
                Artifact.artifact_type == "change_brief",
            )
        )
    assert brief is not None
    previous_failure = brief.payload["previous_failure"]
    assert {key: value for key, value in previous_failure.items() if key != "artifact_types"} == {
        "run_id": failed["run_id"],
        "stage": "engineer",
        "error_code": "CHANGE_PIPELINE_FAILED",
        "error_message": "Mock LLM failure requested for engineer-change",
    }
    assert set(previous_failure["artifact_types"]) == {
        "architecture_spec",
        "architecture_design",
        "base_source_snapshot",
        "blueprint",
        "change_brief",
        "product_spec",
        "requirement_delta",
        "source_context",
    }


def test_invalid_source_change_fails_without_creating_a_version(
    client: TestClient,
    monkeypatch,
) -> None:
    initial = _build_project(client)
    project_id = initial["project_id"]
    original = MockLLMProvider.create_source_file_change_set

    def tampered_change(self, *args, **kwargs):
        change_set = original(self, *args, **kwargs)
        first = change_set.changes[0].model_copy(update={"before_hash": "0" * 64})
        return change_set.model_copy(update={"changes": [first, *change_set.changes[1:]]})

    monkeypatch.setattr(MockLLMProvider, "create_source_file_change_set", tampered_change)
    proposal = _propose_change(
        client,
        project_id,
        "把标题改成“不会提交的版本”",
    )
    failed = _approve_change(client, project_id, proposal["proposal_id"])

    assert failed["status"] == "failed"
    assert failed["error_code"] == "SOURCE_CHANGE_HASH_MISMATCH"
    assert failed["version_id"] is None
    versions = client.get(f"/api/projects/{project_id}/versions").json()
    assert [version["id"] for version in versions] == [initial["version_id"]]
    with client.app.state.testing_session() as db:
        project = db.get(Project, project_id)
        artifacts = set(
            db.scalars(
                select(Artifact.artifact_type).where(Artifact.run_id == failed["run_id"])
            ).all()
        )
    assert project is not None
    assert project.active_write_run_id is None
    assert "source_file_change_set" in artifacts
    assert "source_change_apply_report" not in artifacts
    events = client.get(f"/api/runs/{failed['run_id']}/events/history").json()
    assert "source.change_failed" in [event["type"] for event in events]


def test_project_message_history_is_owner_scoped(client: TestClient) -> None:
    initial = _build_project(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert (
        client.post(
            "/api/auth/signup",
            json={
                "username": "projectintruder",
                "password": "strong-password-123",
                "display_name": "Project Intruder",
            },
        ).status_code
        == 201
    )
    assert client.get(f"/api/projects/{initial['project_id']}/messages").status_code == 404
