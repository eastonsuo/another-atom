from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.agent.orchestrator import Orchestrator
from another_atom.api.dependencies import get_blueprint_executor
from another_atom.contracts.schemas import HumanTaskKind
from another_atom.storage.models import HumanTask, Run


def test_initial_pm_clarification_is_persisted_and_resumes_same_run(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "帮我做一个应用 [pm:clarify]", "mode": "team", "model": "mock"},
    )
    assert created.status_code == 201, created.text
    paused = client.get(f"/api/runs/{created.json()['run_id']}").json()

    assert paused["status"] == "needs_input"
    assert paused["current_stage"] == "product_manager_clarification"
    assert paused["blueprint"] is None
    task = paused["pending_human_task"]
    assert task["kind"] == "input_request"
    assert task["status"] == "pending"

    history = client.get(f"/api/runs/{paused['run_id']}/human-tasks").json()
    assert [item["id"] for item in history] == [task["id"]]

    resumed = client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": "创建一个扫雷游戏，包含计时、插旗和重新开始"},
    )
    assert resumed.status_code == 202, resumed.text
    completed = client.get(f"/api/runs/{paused['run_id']}").json()
    assert completed["run_id"] == paused["run_id"]
    assert completed["status"] == "awaiting_approval"
    approved = client.post(
        f"/api/runs/{paused['run_id']}/approve",
        json={"blueprint": completed["blueprint"]},
    )
    assert approved.status_code == 202
    completed = client.get(f"/api/runs/{paused['run_id']}").json()
    assert completed["status"] == "completed"
    assert completed["version_id"]
    assert completed["pending_human_task"] is None

    messages = client.get(
        f"/api/projects/{paused['project_id']}/messages"
    ).json()
    assert [(message["role"], message["message_type"]) for message in messages] == [
        ("user", "request"),
        ("lead", "clarification"),
        ("user", "clarification_response"),
    ]


def test_human_task_is_owner_scoped(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "帮我做一个应用 [pm:clarify]", "mode": "team", "model": "mock"},
    ).json()
    paused = client.get(f"/api/runs/{created['run_id']}").json()
    task_id = paused["pending_human_task"]["id"]

    assert client.post("/api/auth/logout").status_code == 204
    assert client.post(
        "/api/auth/signup",
        json={
            "username": "human-task-intruder",
            "password": "strong-password-123",
            "display_name": "Intruder",
        },
    ).status_code == 201

    response = client.post(
        f"/api/human-tasks/{task_id}/respond",
        json={"response": "Try to resume another user's Run"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "HUMAN_TASK_NOT_FOUND"


def test_same_response_retry_redispatches_lost_blueprint_execution(
    queued_client: TestClient,
) -> None:
    paused = queued_client.post(
        "/api/runs",
        json={"prompt": "Build an app [pm:clarify]", "mode": "team", "model": "mock"},
    ).json()
    task = queued_client.get(f"/api/runs/{paused['run_id']}").json()[
        "pending_human_task"
    ]
    queued_client.app.dependency_overrides[get_blueprint_executor] = lambda: lambda _run_id: None
    response_text = "Build a timer with start, pause, and reset"
    first = queued_client.post(
        f"/api/human-tasks/{task['id']}/respond", json={"response": response_text}
    )
    assert first.status_code == 202
    assert first.json()["status"] == "product_running"

    from functools import partial

    from another_atom.agent.tasks import execute_blueprint_background

    queued_client.app.dependency_overrides[get_blueprint_executor] = lambda: partial(
        execute_blueprint_background,
        session_factory=queued_client.app.state.testing_session,
        job_dispatcher=lambda _job_id: None,
    )
    retried = queued_client.post(
        f"/api/human-tasks/{task['id']}/respond", json={"response": response_text}
    )
    assert retried.status_code == 202
    resumed = queued_client.get(f"/api/runs/{paused['run_id']}").json()
    assert resumed["status"] == "awaiting_approval"
    assert resumed["pending_human_task"]["kind"] == "approval"


def test_input_response_cannot_revive_non_waiting_run(queued_client: TestClient) -> None:
    paused = queued_client.post(
        "/api/runs",
        json={"prompt": "Build an app [pm:clarify]", "mode": "team", "model": "mock"},
    ).json()
    paused = queued_client.get(f"/api/runs/{paused['run_id']}").json()
    task = paused["pending_human_task"]
    with queued_client.app.state.testing_session() as db:
        run = db.get(Run, paused["run_id"])
        assert run is not None
        run.status = "failed"
        db.commit()

    response = queued_client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": "Build a timer"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "HUMAN_TASK_RUN_NOT_WAITING"
    history = queued_client.get(f"/api/runs/{paused['run_id']}/human-tasks").json()
    assert history[-1]["status"] == "pending"


def test_repeated_resolved_subject_creates_a_new_pending_human_task(
    queued_client: TestClient,
) -> None:
    paused = queued_client.post(
        "/api/runs",
        json={"prompt": "Build an app [pm:clarify]", "mode": "team", "model": "mock"},
    ).json()
    paused = queued_client.get(f"/api/runs/{paused['run_id']}").json()
    with queued_client.app.state.testing_session() as db:
        run = db.get(Run, paused["run_id"])
        original = db.scalar(select(HumanTask).where(HumanTask.run_id == paused["run_id"]))
        assert run is not None and original is not None
        original.status = "answered"
        original.response = {"text": "Still not enough information"}
        created = Orchestrator(db)._create_human_task(
            run,
            kind=HumanTaskKind(original.kind),
            stage=original.stage,
            prompt=original.prompt,
            subject=f"pm:{run.prompt}:{original.prompt}",
        )
        db.commit()
        assert created.id != original.id
        assert created.status == "pending"
