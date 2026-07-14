from fastapi.testclient import TestClient


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
