from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.build.worker import process_next_job
from another_atom.storage.models import Artifact, Project, ProjectVersion, Run


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
    if run.json()["status"] == "build_queued":
        assert process_next_job(client.app.state.testing_session, worker_id="initial-worker")
        run = client.get(f"/api/runs/{run_id}")
    assert run.json()["status"] == "completed"
    return run.json()


def test_project_chat_modifies_existing_code_and_creates_ai_edit_version(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    deployment = client.post(
        f"/api/projects/{initial['project_id']}/publish",
        json={"version_id": initial["version_id"], "strategy": "specify_version"},
    ).json()

    changed = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": '把标题改成“夜间扫雷”，保留计时和插旗逻辑', "model": "mock"},
    )

    assert changed.status_code == 202, changed.text
    run = changed.json()
    assert run["status"] == "completed"
    assert run["trigger"] == "ai_edit"
    assert run["base_version_id"] == initial["version_id"]
    assert run["version_id"] != initial["version_id"]
    assert run["app_spec"]["hero_title"] == "夜间扫雷"

    versions = client.get(
        f"/api/projects/{initial['project_id']}/versions"
    ).json()
    assert [(version["number"], version["source"]) for version in versions] == [
        (2, "ai_edit"),
        (1, "build"),
    ]
    assert versions[0]["git_commit"] != versions[1]["git_commit"]

    messages = client.get(
        f"/api/projects/{initial['project_id']}/messages"
    ).json()
    assert [(message["role"], message["message_type"]) for message in messages] == [
        ("user", "request"),
        ("user", "request"),
        ("lead", "change_brief"),
        ("system", "result"),
    ]
    assert messages[1]["payload"]["base_version_id"] == initial["version_id"]

    public_app = client.get(f"/api/public/{deployment['public_id']}").json()
    assert public_app["hero_title"] != "夜间扫雷"
    with client.app.state.testing_session() as db:
        artifacts = set(
            db.scalars(
                select(Artifact.artifact_type).where(Artifact.run_id == run["run_id"])
            ).all()
        )
    assert {
        "change_brief",
        "requirement_delta",
        "base_source_snapshot",
        "source_context",
        "source_diff",
        "architecture_spec",
        "app_spec",
        "data_profile",
        "validation_report",
        "review_report",
    } <= artifacts
    with client.app.state.testing_session() as db:
        source_context = db.scalar(
            select(Artifact).where(
                Artifact.run_id == run["run_id"],
                Artifact.artifact_type == "source_context",
            )
        )
        assert source_context is not None
        assert source_context.payload["trimming_applied"] is False
        assert {item["path"] for item in source_context.payload["included_files"]} == {
            "app-spec.json",
            "index.html",
            "styles.css",
            "app.js",
        }


def test_pm_clarification_resumes_same_project_change_run(client: TestClient) -> None:
    initial = _build_project(client)
    paused = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "改一下 [pm:clarify]", "model": "mock"},
    )

    assert paused.status_code == 202, paused.text
    run = paused.json()
    assert run["status"] == "needs_input"
    assert run["current_stage"] == "product_manager_clarification"
    task = run["pending_human_task"]
    assert task["kind"] == "input_request"
    assert task["status"] == "pending"

    resumed = client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": '把标题改成“澄清后的扫雷”，其他功能保持不变'},
    )
    assert resumed.status_code == 202, resumed.text
    completed = client.get(f"/api/runs/{run['run_id']}").json()
    assert completed["run_id"] == run["run_id"]
    assert completed["status"] == "completed"
    assert completed["app_spec"]["hero_title"] == "澄清后的扫雷"
    assert completed["pending_human_task"] is None

    messages = client.get(
        f"/api/projects/{initial['project_id']}/messages"
    ).json()
    assert [(message["role"], message["message_type"]) for message in messages[-5:]] == [
        ("user", "request"),
        ("lead", "clarification"),
        ("user", "clarification_response"),
        ("lead", "change_brief"),
        ("system", "result"),
    ]

    duplicate = client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": '把标题改成“澄清后的扫雷”，其他功能保持不变'},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["run_id"] == run["run_id"]


def test_project_chat_direct_answer_does_not_create_a_version(client: TestClient) -> None:
    initial = _build_project(client)
    answered = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "这个项目使用了哪些颜色？", "model": "mock"},
    )

    assert answered.status_code == 202, answered.text
    run = answered.json()
    assert run["status"] == "completed"
    assert run["version_id"] is None
    versions = client.get(
        f"/api/projects/{initial['project_id']}/versions"
    ).json()
    assert [version["id"] for version in versions] == [initial["version_id"]]
    messages = client.get(
        f"/api/projects/{initial['project_id']}/messages"
    ).json()
    assert messages[-1]["role"] == "lead"
    assert messages[-1]["message_type"] == "answer"
    with client.app.state.testing_session() as db:
        project = db.get(Project, initial["project_id"])
        assert project is not None
        assert project.active_write_run_id is None


def test_failed_first_build_continues_in_the_same_project(client: TestClient) -> None:
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
    assert failed["status"] == "failed"
    assert failed["version_id"] is None

    recovered = client.post(
        f"/api/projects/{failed['project_id']}/messages",
        json={
            "message": "继续原项目：创建一个扫雷游戏，包含计时、插旗和重新开始",
            "model": "mock",
        },
    )
    assert recovered.status_code == 202, recovered.text
    resumed = recovered.json()
    assert resumed["project_id"] == failed["project_id"]
    assert resumed["run_id"] != failed["run_id"]
    resumed = client.get(f"/api/runs/{resumed['run_id']}").json()
    assert resumed["status"] == "completed"
    assert resumed["version_id"]

    projects = client.get("/api/projects").json()
    assert [project["id"] for project in projects] == [failed["project_id"]]
    messages = client.get(
        f"/api/projects/{failed['project_id']}/messages"
    ).json()
    assert [(message["role"], message["message_type"]) for message in messages] == [
        ("user", "request"),
        ("system", "error"),
        ("user", "request"),
    ]
    assert messages[-1]["payload"]["request_type"] == "failure_recovery"
    assert messages[-1]["payload"]["retry_of_run_id"] == failed["run_id"]


def test_waiting_clarification_becomes_stale_when_base_version_changes(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    paused = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "改一下 [pm:clarify]", "model": "mock"},
    ).json()
    task = paused["pending_human_task"]

    completed = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "把主色改成蓝色", "model": "mock"},
    )
    assert completed.status_code == 202
    assert completed.json()["status"] == "completed"

    stale = client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": "把标题改成新的标题"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "BASE_VERSION_CHANGED"
    history = client.get(f"/api/runs/{paused['run_id']}/human-tasks").json()
    assert history[-1]["status"] == "stale"
    stale_run = client.get(f"/api/runs/{paused['run_id']}").json()
    assert stale_run["status"] == "cancelled"
    assert stale_run["error_code"] == "BASE_VERSION_CHANGED"
    assert stale_run["pending_human_task"] is None
    messages = client.get(f"/api/projects/{paused['project_id']}/messages").json()
    assert messages[-1]["role"] == "system"
    assert messages[-1]["message_type"] == "error"
    assert messages[-1]["payload"]["code"] == "BASE_VERSION_CHANGED"

def test_project_allows_only_one_active_code_writer(queued_client: TestClient) -> None:
    initial = _build_project(queued_client)
    first = queued_client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "把主色改成蓝色", "model": "mock"},
    )
    assert first.status_code == 202
    assert first.json()["status"] == "build_queued"

    second = queued_client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "再修改标题", "model": "mock"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "PROJECT_WRITE_BUSY"

    assert process_next_job(queued_client.app.state.testing_session, worker_id="change-worker")
    completed = queued_client.get(f"/api/runs/{first.json()['run_id']}").json()
    assert completed["status"] == "completed"
    with queued_client.app.state.testing_session() as db:
        project = db.get(Project, initial["project_id"])
        assert project is not None
        assert project.active_write_run_id is None


def test_failed_change_preserves_base_version_and_releases_project_lock(
    client: TestClient,
) -> None:
    initial = _build_project(client)
    failed = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "修改标题 [fail:lead]", "model": "mock"},
    )
    assert failed.status_code == 202
    assert failed.json()["status"] == "failed"
    with client.app.state.testing_session() as db:
        project = db.get(Project, initial["project_id"])
        run = db.get(Run, failed.json()["run_id"])
        versions = db.scalars(
            select(ProjectVersion).where(ProjectVersion.project_id == initial["project_id"])
        ).all()
        assert project is not None and run is not None
        assert project.latest_version_id == initial["version_id"]
        assert project.active_write_run_id is None
        assert len(versions) == 1
    messages = client.get(
        f"/api/projects/{initial['project_id']}/messages"
    ).json()
    assert messages[-1]["message_type"] == "error"

    continued = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": '继续，把标题改成“恢复后的扫雷”', "model": "mock"},
    )
    assert continued.status_code == 202, continued.text
    assert continued.json()["status"] == "completed"
    assert continued.json()["base_version_id"] == initial["version_id"]
    with client.app.state.testing_session() as db:
        brief = db.scalar(
            select(Artifact).where(
                Artifact.run_id == continued.json()["run_id"],
                Artifact.artifact_type == "change_brief",
            )
        )
        assert brief is not None
        assert brief.payload["previous_failure"] == {
            "run_id": failed.json()["run_id"],
            "stage": "team_leader",
            "error_code": "CHANGE_PIPELINE_FAILED",
            "error_message": "Mock LLM failure requested for lead",
            "artifact_types": [],
        }

    later = client.post(
        f"/api/projects/{initial['project_id']}/messages",
        json={"message": "再把主色改成蓝色", "model": "mock"},
    )
    assert later.status_code == 202, later.text
    assert later.json()["status"] == "completed"
    with client.app.state.testing_session() as db:
        later_brief = db.scalar(
            select(Artifact).where(
                Artifact.run_id == later.json()["run_id"],
                Artifact.artifact_type == "change_brief",
            )
        )
        assert later_brief is not None
        assert later_brief.payload["previous_failure"] is None


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
