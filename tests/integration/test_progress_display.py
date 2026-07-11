"""Runtime verification of the studio progress display contract.

These tests drive real end-to-end runs (mock provider) and assert the exact
`status` / `current_stage` values plus the persisted event stream that the
studio frontend relies on to render the pipeline timeline, status pills, and
the progress/animation states. They exist to catch regressions where the
backend emits a stage/status the frontend cannot map (which would freeze the
progress display or leave every step stuck on "Waiting").
"""

from fastapi.testclient import TestClient

# Stage identifiers the frontend Timeline knows how to render (App.tsx).
# team mode: team_leader, product_manager, [blueprint_approval], architect,
# engineer, build, data, complete. build_queue is display-mapped to engineer.
FRONTEND_TEAM_STAGES = {
    "team_leader",
    "product_manager",
    "blueprint_approval",
    "architect",
    "engineer",
    "build",
    "data",
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
    "completed",
    "completed_degraded",
    "failed",
    "cancelled",
}


def _create_team_run(client: TestClient, prompt: str) -> dict:
    created = client.post("/api/runs", json={"prompt": prompt, "mode": "team"}).json()
    return client.get(f"/api/runs/{created['run_id']}").json()


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
    for expected in ("product_manager", "architect", "engineer", "build", "data", "complete"):
        assert expected in stages, f"missing progress stage: {expected}"


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


def test_out_of_scope_request_stops_at_needs_input_scope_review(client: TestClient) -> None:
    """An out-of-scope request must settle on needs_input / scope_review.

    Regression guard for the studio freeze bug: a request the V1 catalog cannot
    build (e.g. a CRM / a game like Minesweeper) used to leave the main
    workspace stuck on the looping "Engineer is working" animation. The
    frontend only switches to the ScopeStop / needs-input view when the run
    settles on status ``needs_input`` at stage ``scope_review`` (a terminal
    state the polling loop stops on), so we lock that contract here and confirm
    a rewrite suggestion is surfaced for the user to act on.
    """
    run = _create_team_run(client, "Build a CRM for my sales team")

    assert run["status"] in FRONTEND_STATUSES
    assert run["status"] == "needs_input"
    assert run["current_stage"] in FRONTEND_TEAM_STAGES
    assert run["current_stage"] == "scope_review"
    # No build artifact/version is produced for an out-of-scope request.
    assert not run["version_id"]

    events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
    assert events
    needs_input_events = [event for event in events if event["type"] == "run.needs_input"]
    assert needs_input_events, "no run.needs_input event -> frontend can't render ScopeStop"
    payload = needs_input_events[-1]["payload"]
    assert payload.get("stage") == "scope_review"
    assert isinstance(payload.get("message"), str) and payload["message"]
    # The PM draft is what ScopeStop asks the user to confirm; it must be a
    # concrete, buildable catalog request rather than generic rewrite advice.
    assert isinstance(payload.get("rewrite_suggestion"), str) and payload["rewrite_suggestion"]
    suggestion = payload["rewrite_suggestion"].lower()
    assert "catalog" in suggestion
    assert "home" in suggestion
    assert "product" in suggestion


def test_confirmed_catalog_alternative_skips_second_product_manager_pass(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a CRM for my sales team")
    assert source["status"] == "needs_input"
    suggestion = source["blueprint"]["rewrite_suggestion"]

    response = client.post(
        f"/api/runs/{source['run_id']}/confirm-alternative",
        json={"prompt": suggestion},
    )
    assert response.status_code == 202
    confirmed = response.json()
    assert confirmed["run_id"] != source["run_id"]
    assert confirmed["project_id"] == source["project_id"]
    assert confirmed["blueprint"]["support_level"] == "supported"

    events = client.get(f"/api/runs/{confirmed['run_id']}/events/history").json()
    assert not any(
        event["type"] == "stage.started"
        and event["payload"].get("stage") == "product_manager"
        for event in events
    )
    assert any(
        event["type"] == "artifact.created"
        and "without another Product Manager pass" in event["payload"]["message"]
        for event in events
    )
    assert client.post(
        f"/api/runs/{source['run_id']}/confirm-alternative",
        json={"prompt": suggestion},
    ).status_code == 409


def test_catalog_alternative_cannot_be_edited_back_to_original_game(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a minesweeper game")
    assert source["status"] == "needs_input"

    response = client.post(
        f"/api/runs/{source['run_id']}/confirm-alternative",
        json={"prompt": "扫雷游戏"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ALTERNATIVE_OUT_OF_SCOPE"
    assert client.get(f"/api/runs/{source['run_id']}").json()["status"] == "needs_input"


def test_user_can_ask_product_manager_to_regenerate_the_requirement_draft(
    client: TestClient,
) -> None:
    source = _create_team_run(client, "Build a minesweeper game")
    response = client.post(
        f"/api/runs/{source['run_id']}/regenerate-alternative",
        json={"prompt": "做一个复古像素风扫雷游戏"},
    )

    assert response.status_code == 202
    regenerated = response.json()
    assert regenerated["project_id"] == source["project_id"]
    assert regenerated["run_id"] != source["run_id"]
    regenerated = client.get(f"/api/runs/{regenerated['run_id']}").json()
    assert regenerated["status"] == "needs_input"
    assert regenerated["blueprint"]["support_level"] == "unsupported"
    assert regenerated["build_job_id"] is None
    suggestion = regenerated["blueprint"]["rewrite_suggestion"]
    assert isinstance(suggestion, str) and suggestion
    assert "catalog" in suggestion.lower() or "商品" in suggestion

    second_response = client.post(
        f"/api/runs/{regenerated['run_id']}/regenerate-alternative",
        json={"prompt": suggestion},
    )
    assert second_response.status_code == 202
    second = client.get(f"/api/runs/{second_response.json()['run_id']}").json()
    assert second["status"] == "needs_input"
    assert second["build_job_id"] is None
