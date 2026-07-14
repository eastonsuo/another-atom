from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

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
        run_count = db.scalar(
            select(func.count(Run.id)).where(Run.project_id == project_id)
        )
        job_count = db.scalar(
            select(func.count(BuildJob.id)).where(BuildJob.project_id == project_id)
        )
        version_count = db.scalar(
            select(func.count(ProjectVersion.id)).where(
                ProjectVersion.project_id == project_id
            )
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
    response = client.post(
        f"/api/projects/{project_id}/change-proposals/{proposal_id}/approve"
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_project_chat_proposes_then_modifies_existing_code(
    client: TestClient,
) -> None:
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
        '把标题改成“夜间扫雷”，保留计时和插旗逻辑',
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
    assert public_app["hero_title"] != "夜间扫雷"
    with client.app.state.testing_session() as db:
        artifacts = set(
            db.scalars(
                select(Artifact.artifact_type).where(Artifact.run_id == run["run_id"])
            ).all()
        )
        source_context = db.scalar(
            select(Artifact).where(
                Artifact.run_id == run["run_id"],
                Artifact.artifact_type == "source_context",
            )
        )
    assert {
        "change_brief",
        "requirement_delta",
        "base_source_snapshot",
        "source_context",
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
    assert source_context.payload["trimming_applied"] is False
    assert {item["path"] for item in source_context.payload["included_files"]} == {
        "app-spec.json",
        "index.html",
        "styles.css",
        "app.js",
        "tests/app.test.js",
    }


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
        '把标题改成“澄清后的扫雷”，其他功能保持不变',
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


def test_failed_first_build_requires_proposal_approval_to_continue(
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
        f"/api/projects/{project_id}/change-proposals/"
        f"{stale_proposal['proposal_id']}/approve"
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
        '继续，把标题改成“恢复后的扫雷”',
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
    assert {
        key: value for key, value in previous_failure.items() if key != "artifact_types"
    } == {
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


def test_project_message_history_is_owner_scoped(client: TestClient) -> None:
    initial = _build_project(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post(
        "/api/auth/signup",
        json={
            "username": "projectintruder",
            "password": "strong-password-123",
            "display_name": "Project Intruder",
        },
    ).status_code == 201
    assert (
        client.get(f"/api/projects/{initial['project_id']}/messages").status_code
        == 404
    )
