from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import select

from another_atom.storage.models import Deployment, Project, ProjectVersion, UsageLedger

PROMPT = (
    "Build a restrained product catalog called Mono Market for useful home objects. "
    "Use editorial photography and a coral accent."
)


def create_and_build(client: TestClient, prompt: str = PROMPT, mode: str = "team"):
    created = client.post("/api/runs", json={"prompt": prompt, "mode": mode})
    assert created.status_code == 201, created.text
    initial = created.json()
    assert initial["status"] == "product_running"
    assert initial["blueprint"] is None
    run = client.get(f"/api/runs/{initial['run_id']}").json()
    assert run["blueprint"]["support_level"] == "supported"
    assert run["status"] == "awaiting_approval"
    approved = client.post(
        f"/api/runs/{run['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    assert approved.status_code == 202, approved.text
    return client.get(f"/api/runs/{run['run_id']}").json()


def test_team_mode_golden_path_to_public_url(client: TestClient) -> None:
    model_config = client.get("/api/models")
    assert model_config.status_code == 200
    assert model_config.json()["default_model"] == "mock"
    assert model_config.json()["sandbox_available"] is False
    run = create_and_build(client)
    assert run["status"] == "completed"
    assert run["validation_report"]["passed"] is True
    assert run["data_profile"] is None
    assert run["review_report"] is None
    assert run["execution_report"]["status"] == "passed"
    assert run["model"] == "mock"
    assert run["version_id"]
    quota = client.get("/api/quota").json()
    assert quota["used"] == 3
    assert quota["reserved"] == 0
    with client.app.state.testing_session() as db:
        settles = db.scalars(
            select(UsageLedger)
            .where(
                UsageLedger.run_id == run["run_id"],
                UsageLedger.entry_type == "settle",
            )
            .order_by(UsageLedger.created_at)
        ).all()
    assert [entry.stage for entry in settles] == [
        "product_manager",
        "architect",
        "engineer",
    ]
    assert [entry.request_count for entry in settles] == [1, 1, 1]

    versions = client.get(f"/api/projects/{run['project_id']}/versions")
    assert versions.status_code == 200
    assert [item["number"] for item in versions.json()] == [1]

    preview = client.get(f"/api/previews/{run['version_id']}")
    assert preview.status_code == 200
    assert preview.json()["project_name"] == "Mono Market"

    published = client.post(
        f"/api/projects/{run['project_id']}/publish",
        json={"version_id": run["version_id"], "strategy": "specify_version"},
    )
    assert published.status_code == 200
    public_app = client.get(f"/api/public/{published.json()['public_id']}")
    assert public_app.status_code == 200
    assert public_app.json() == preview.json()


def test_edit_restore_and_export_preserve_version_history(client: TestClient) -> None:
    run = create_and_build(client, mode="engineer")
    edited = client.post(
        f"/api/projects/{run['project_id']}/revisions",
        json={"hero_title": "Objects with a point of view"},
    )
    assert edited.status_code == 200
    assert edited.json()["number"] == 2
    assert edited.json()["source"] == "edit"

    restored = client.post(f"/api/projects/{run['project_id']}/restore/{run['version_id']}")
    assert restored.status_code == 200
    assert restored.json()["number"] == 3
    assert restored.json()["source"] == "restore"

    exported = client.get(f"/api/projects/{run['project_id']}/export")
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["schema_version"] == "1.0"
    assert [version["source"] for version in payload["versions"]] == [
        "build",
        "edit",
        "restore",
    ]
    serialized = exported.text.lower()
    for forbidden in ("api_key", "secret", "usage_ledger", "absolute_path"):
        assert forbidden not in serialized


def test_restore_last_usable_skips_failed_history_and_keeps_public_version(
    client: TestClient,
) -> None:
    run = create_and_build(client, mode="engineer")
    first = client.get(f"/api/projects/{run['project_id']}/versions").json()[0]
    published = client.post(
        f"/api/projects/{run['project_id']}/publish",
        json={"version_id": first["id"], "strategy": "specify_version"},
    )
    assert published.status_code == 200

    edited = client.post(
        f"/api/projects/{run['project_id']}/revisions",
        json={"hero_title": "This candidate is no longer usable"},
    ).json()
    with client.app.state.testing_session() as db:
        edited_version = db.get(ProjectVersion, edited["id"])
        assert edited_version is not None
        failed_report = dict(edited_version.validation_report)
        failed_report["passed"] = False
        edited_version.validation_report = failed_report
        db.commit()

    restored = client.post(
        f"/api/projects/{run['project_id']}/restore-last-usable"
    )
    assert restored.status_code == 200, restored.text
    payload = restored.json()
    assert payload["number"] == 3
    assert payload["source"] == "restore"
    assert payload["run_id"] == first["run_id"]
    assert payload["app_spec"]["hero_title"] == first["app_spec"]["hero_title"]
    assert payload["git_commit"] not in {first["git_commit"], edited["git_commit"]}

    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        deployment = db.scalar(
            select(Deployment).where(Deployment.project_id == run["project_id"])
        )
        assert project is not None
        assert project.latest_version_id == payload["id"]
        assert project.active_write_run_id is None
        assert deployment is not None and deployment.version_id == first["id"]


def test_restore_rejects_an_active_project_writer(client: TestClient) -> None:
    run = create_and_build(client, mode="engineer")
    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        assert project is not None
        project.active_write_run_id = "another-operation"
        db.commit()

    response = client.post(
        f"/api/projects/{run['project_id']}/restore-last-usable"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PROJECT_WRITE_BUSY"


def test_restore_last_usable_releases_the_lock_when_revalidation_fails(
    client: TestClient,
) -> None:
    run = create_and_build(client, mode="engineer")
    with client.app.state.testing_session() as db:
        version = db.get(ProjectVersion, run["version_id"])
        assert version is not None
        broken_app_spec = dict(version.app_spec)
        broken_app_spec["pages"] = broken_app_spec["pages"][:1]
        broken_app_spec["products"] = []
        broken_app_spec["javascript"] = "eval('not allowed')"
        version.app_spec = broken_app_spec
        db.commit()

    response = client.post(
        f"/api/projects/{run['project_id']}/restore-last-usable"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "NO_USABLE_VERSION"
    assert len(client.get(f"/api/projects/{run['project_id']}/versions").json()) == 1
    with client.app.state.testing_session() as db:
        project = db.get(Project, run["project_id"])
        assert project is not None and project.active_write_run_id is None


def test_events_and_project_state_are_recoverable(client: TestClient) -> None:
    run = create_and_build(client)
    events = client.get(f"/api/runs/{run['run_id']}/events/history")
    assert events.status_code == 200
    event_types = [event["type"] for event in events.json()]
    assert "approval.required" in event_types
    assert "approval.confirmed" in event_types
    assert "build.queued" in event_types
    assert "executor.validation.completed" in event_types
    assert event_types[-1] == "run.completed"

    latest = client.get(f"/api/projects/{run['project_id']}/runs/latest")
    assert latest.status_code == 200
    assert latest.json()["version_id"] == run["version_id"]


def test_unpublish_removes_public_access(client: TestClient) -> None:
    run = create_and_build(client)
    deployment = client.post(
        f"/api/projects/{run['project_id']}/publish",
        json={"version_id": run["version_id"], "strategy": "always_latest"},
    ).json()
    response = client.post(f"/api/projects/{run['project_id']}/unpublish")
    assert response.status_code == 204
    assert client.get(f"/api/public/{deployment['public_id']}").status_code == 404


def test_golden_path_completes_five_out_of_five(client: TestClient) -> None:
    completed = 0
    for index in range(5):
        started = perf_counter()
        created = client.post(
            "/api/runs",
            json={
                "prompt": f"Build a product catalog called Acceptance {index}",
                "mode": "team",
            },
        )
        assert created.status_code == 201
        assert perf_counter() - started < 1.0
        initial = created.json()
        run = client.get(f"/api/runs/{initial['run_id']}").json()
        initial_events = client.get(f"/api/runs/{run['run_id']}/events/history").json()
        assert initial_events
        assert perf_counter() - started < 2.0
        approved = client.post(
            f"/api/runs/{run['run_id']}/approve",
            json={"blueprint": run["blueprint"]},
        )
        assert approved.status_code == 202
        current = client.get(f"/api/runs/{run['run_id']}").json()
        completed += current["status"] == "completed"
    assert completed == 5
