"""Runtime verification of the studio progress display contract.

These tests drive real end-to-end runs (mock provider) and assert the exact
`status` / `current_stage` values plus the persisted event stream that the
studio frontend relies on to render the pipeline timeline, status pills, and
the progress/animation states. They exist to catch regressions where the
backend emits a stage/status the frontend cannot map (which would freeze the
progress display or leave every step stuck on "Waiting").
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from another_atom.agent.orchestrator import Orchestrator

# Stage identifiers the frontend Timeline knows how to render (App.tsx).
# team mode: team_leader, product_manager, [blueprint_approval], architect,
# engineer, data, build, reviewer, complete. build_queue is display-mapped to engineer.
FRONTEND_TEAM_STAGES = {
    "team_leader",
    "product_manager",
    "product_manager_clarification",
    "blueprint_approval",
    "architect",
    "engineer",
    "build",
    "data",
    "reviewer",
    "complete",
    "build_queue",  # mapped to "engineer" by the frontend
    "scope_review",  # needs_input terminal view (ScopeStop), not a timeline step
}

# Statuses the frontend can render as a StatusPill / drive the timeline with.
FRONTEND_STATUSES = {
    "product_running",
    "awaiting_approval",
    "needs_input",
    "build_queued",
    "architect_running",
    "engineer_running",
    "building",
    "data_running",
    "review_running",
    "completed",
    "completed_degraded",
    "failed",
    "cancelled",
}


def _create_team_run(client: TestClient, prompt: str) -> dict:
    created = client.post("/api/runs", json={"prompt": prompt, "mode": "team"}).json()
    run = client.get(f"/api/runs/{created['run_id']}").json()
    if run["status"] == "awaiting_approval" and run["blueprint"]["support_level"] == "supported":
        approved = client.post(
            f"/api/runs/{run['run_id']}/approve",
            json={"blueprint": run["blueprint"]},
        )
        assert approved.status_code == 202, approved.text
        run = client.get(f"/api/runs/{run['run_id']}").json()
    return run


def test_supported_run_reaches_completed_with_frontend_mappable_stages(
    client: TestClient,
) -> None:
    """A plain supported catalog build should march to `completed`.

    The `client` fixture dispatches the build job synchronously, so the run is
    already terminal by the time we read it back. We assert the final state and
    that every persisted event carries a frontend-renderable stage, which is
    what keeps the timeline advancing and the completion animation firing.
    """
    run = _create_team_run(client, "Build a product catalog for home objects")

    assert run["status"] in {"completed", "completed_degraded"}
    assert run["current_stage"] == "complete"
    assert run["version_id"]

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert events, "no persisted events -> progress display would be empty"

    # Events must be strictly ordered (frontend sorts by sequence for the
    # timeline + debug panel; gaps or bad stages freeze the display).
    sequences = [event["sequence"] for event in events]
    assert sequences == sorted(sequences)

    stages = {event["payload"].get("stage") for event in events}
    stages.discard(None)
    unknown = stages - FRONTEND_TEAM_STAGES
    assert not unknown, f"backend emitted stages the timeline cannot render: {unknown}"

    # The full supported pipeline must visibly pass through each build step so
    # the timeline lights up sequentially rather than jumping to done.
    for expected in (
        "product_manager",
        "architect",
        "engineer",
        "build",
        "complete",
    ):
        assert expected in stages, f"missing progress stage: {expected}"

    engineer_events = [event for event in events if event["payload"].get("stage") == "engineer"]
    engineer_event_types = [event["type"] for event in engineer_events]
    assert "engineer.context.prepared" in engineer_event_types
    assert "agent.attempt.started" in engineer_event_types
    assert "agent.output.validated" in engineer_event_types
    assert engineer_event_types.index("engineer.context.prepared") < engineer_event_types.index(
        "agent.attempt.started"
    )
    assert engineer_event_types.index("agent.attempt.started") < engineer_event_types.index(
        "agent.output.validated"
    )


def test_adapted_run_pauses_at_awaiting_approval_stage(client: TestClient) -> None:
    """An adapted-scope request pauses with a stage the timeline can show.

    This guards the human-in-the-loop pause: status `awaiting_approval` and
    stage `blueprint_approval` must both be renderable, otherwise the progress
    display would stall on an unknown state.
    """
    run = _create_team_run(client, "Build a product catalog with login")

    assert run["status"] in FRONTEND_STATUSES
    assert run["status"] == "awaiting_approval"
    assert run["current_stage"] in FRONTEND_TEAM_STAGES
    assert run["current_stage"] == "blueprint_approval"
    assert run["pending_human_task"]["kind"] == "approval"
    assert run["pending_human_task"]["status"] == "pending"

    approved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    completed = client.get(f"/api/runs/{run['run_id']}").json()
    assert completed["status"] in {"completed", "completed_degraded"}
    assert completed["pending_human_task"] is None
    tasks = client.get(f"/api/runs/{run['run_id']}/human-tasks").json()
    assert tasks[-1]["status"] == "approved"


def test_all_persisted_events_expose_message_and_valid_stage(client: TestClient) -> None:
    """Every event must carry a message + mappable stage.

    The debug panel and the "Recent events" progress feed render
    `payload.message`; a missing message would show a blank/`undefined` line.
    """
    run = _create_team_run(client, "Build a minimalist lighting catalog")
    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()

    assert events
    for event in events:
        assert event["type"], "event without a type breaks the debug panel header"
        assert isinstance(event["payload"].get("message"), str) and event["payload"]["message"], (
            "event without a message string would render blank in the progress feed"
        )
        stage = event["payload"].get("stage")
        if stage is not None:
            assert stage in FRONTEND_TEAM_STAGES
        timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert timestamp.utcoffset() == timedelta(0), (
            "event timestamp without an explicit UTC offset makes Studio add the browser timezone"
        )


def test_provider_lifecycle_events_are_persisted_for_replay(
    queued_client: TestClient,
) -> None:
    run = _create_team_run(queued_client, "Build a product catalog with login")
    session_factory = queued_client.app.state.testing_session

    with session_factory() as db:
        handler = Orchestrator(db)._provider_event_handler(run["run_id"], "engineer")
        handler(
            "provider.request.started",
            {"provider": "ollama", "request_attempt": 1, "stream": True},
        )
        handler(
            "provider.first_token",
            {"provider": "ollama", "request_attempt": 1},
        )

    events = queued_client.get(f"/api/runs/{run['run_id']}/events/history").json()
    provider_events = [event for event in events if event["type"].startswith("provider.")]

    assert [event["type"] for event in provider_events[-2:]] == [
        "provider.request.started",
        "provider.first_token",
    ]
    assert all(event["payload"]["stage"] == "engineer" for event in provider_events[-2:])
    assert all(event["payload"]["provider"] == "ollama" for event in provider_events[-2:])


def test_visible_agent_message_is_persisted_and_replayable(
    queued_client: TestClient,
) -> None:
    run = _create_team_run(queued_client, "Build a product catalog with login")
    session_factory = queued_client.app.state.testing_session
    message_id = "11111111-1111-4111-8111-111111111111"

    with session_factory() as db:
        handler = Orchestrator(db)._provider_event_handler(run["run_id"], "engineer")
        handler(
            "agent.message.started",
            {"message_id": message_id, "role": "Engineer（工程师）"},
        )
        handler(
            "agent.message.delta",
            {
                "message_id": message_id,
                "role": "Engineer（工程师）",
                "delta": "我正在生成并校验应用源码。",
            },
        )
        handler(
            "agent.output.delta",
            {
                "message_id": message_id,
                "role": "Engineer（工程师）",
                "delta": '{"message":"正在生成","result":',
            },
        )
        handler(
            "agent.message.completed",
            {"message_id": message_id, "role": "Engineer（工程师）"},
        )

    messages = queued_client.get(f"/api/projects/{run['project_id']}/messages").json()
    visible = next(message for message in messages if message["id"] == message_id)
    assert visible["run_id"] == run["run_id"]
    assert visible["role"] == "engineer"
    assert visible["message_type"] == "agent_update"
    assert visible["content"] == "我正在生成并校验应用源码。"
    assert visible["payload"]["status"] == "completed"
    assert visible["payload"]["model_output"] == '{"message":"正在生成","result":'

    events = queued_client.get(f"/api/runs/{run['run_id']}/events/history").json()
    message_events = [event for event in events if event["type"].startswith("agent.message.")]
    output_events = [event for event in events if event["type"] == "agent.output.delta"]
    assert [event["type"] for event in message_events[-3:]] == [
        "agent.message.started",
        "agent.message.delta",
        "agent.message.completed",
    ]
    assert output_events[-1]["payload"]["delta"] == '{"message":"正在生成","result":'


def test_non_web_request_reaches_approvable_source_delivery(client: TestClient) -> None:
    run = _create_team_run(client, "Build a native iOS camera app")

    assert run["status"] in FRONTEND_STATUSES
    assert run["status"] == "awaiting_approval"
    assert run["current_stage"] == "blueprint_approval"
    assert run["blueprint"]["product_type"] == "native_application"
    assert run["blueprint"]["capability_policy_version"] == "source-v1"
    assert not run["version_id"]

    approved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    completed = client.get(f"/api/runs/{run['run_id']}").json()
    assert completed["status"] == "completed_degraded"
    assert completed["current_stage"] == "complete"
    assert completed["source_bundle"]["runtime_binding"] is None
    assert completed["execution_report"] is None
    assert completed["version_id"]


def test_source_only_delivery_does_not_create_a_fake_runtime_execution(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a native iOS camera app")
    approved = client.post(
        f"/api/runs/{source['run_id']}/approve",
        json={"blueprint": source["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    completed = client.get(f"/api/runs/{source['run_id']}").json()

    assert completed["status"] == "completed_degraded"
    assert completed["build_job_id"] is not None
    assert completed["execution_report"] is None
    events = client.get(f"/api/runs/{source['run_id']}/events/history").json()
    assert any(event["type"] == "run.source_ready" for event in events)
    assert not any(event["type"].startswith("executor.") for event in events)
    preview = client.get(f"/api/previews/{completed['version_id']}")
    assert preview.status_code == 409
    assert preview.json()["code"] == "PREVIEW_NOT_SUPPORTED"


def test_minesweeper_is_built_as_an_interactive_web_game(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a minesweeper game")
    assert source["status"] in {"completed", "completed_degraded"}
    assert source["blueprint"]["product_type"] == "web_game"
    assert source["blueprint"]["support_level"] == "supported"
    generated = {item["path"]: item["content"] for item in source["source_bundle"]["files"]}
    assert "minefield" in generated["index.html"]
    assert "function reveal" in generated["app.js"]
    assert source["version_id"]
    files = client.get(
        f"/api/projects/{source['project_id']}/files?run_id={source['run_id']}"
    ).json()
    repository_paths = {item["path"] for item in files if item["source"] == "repository"}
    assert {"index.html", "styles.css", "app.js", "app-spec.json"}.issubset(repository_paths)


def test_non_web_request_is_not_forced_through_web_alternative_regeneration(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a native iOS camera app")
    response = client.post(
        f"/api/runs/{source['run_id']}/regenerate-alternative",
        json={"prompt": "做一个复古像素风扫雷游戏"},
    )

    assert response.status_code == 409
    assert source["status"] == "awaiting_approval"
    assert source["blueprint"]["product_type"] == "native_application"
