from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from another_atom.agent.orchestrator import Orchestrator
from another_atom.agent.tasks import recover_interrupted_blueprints
from another_atom.api.routes import approve_blueprint
from another_atom.build.worker import claim_next_job, execute_claimed_job, process_next_job
from another_atom.contracts.schemas import ArtifactType, Blueprint, BlueprintApproval
from another_atom.domain.artifacts import get_artifact
from another_atom.domain.errors import AppError
from another_atom.domain.quota import reserve_quota
from another_atom.storage.models import (
    Approval,
    BuildJob,
    Project,
    ProjectSession,
    ProjectVersion,
    Run,
    UsageLedger,
    User,
    now_utc,
)


def _create_run(client: TestClient, prompt: str = "Build a product catalog") -> dict:
    initial = client.post(
        "/api/runs",
        json={"prompt": prompt, "mode": "team"},
    ).json()
    return client.get(f"/api/runs/{initial['run_id']}").json()


def test_expired_worker_lease_can_be_reclaimed(queued_client: TestClient) -> None:
    created = _create_run(queued_client)
    assert created["status"] == "build_queued"
    session_factory = queued_client.app.state.testing_session
    assert claim_next_job(session_factory, worker_id="dead-worker") == created["build_job_id"]
    with session_factory() as db:
        job = db.get(BuildJob, created["build_job_id"])
        run = db.get(Run, created["run_id"])
        assert job is not None and run is not None
        job.lease_expires_at = now_utc() - timedelta(seconds=1)
        run.status = "build_queued"
        db.commit()

    claimed = claim_next_job(session_factory, worker_id="replacement-worker")
    assert claimed == created["build_job_id"]
    with session_factory() as db:
        job = db.get(BuildJob, claimed)
        assert job is not None
        assert job.lease_owner == "replacement-worker"
        assert job.attempt == 2


def test_interrupted_blueprint_background_task_is_recovered(
    queued_client: TestClient,
) -> None:
    session_factory = queued_client.app.state.testing_session
    with session_factory() as db:
        db.add(
            User(
                id="demo-user",
                display_name="Demo User",
                plan="demo",
                quota_limit=100,
            )
        )
        db.flush()
        project = Project(
            user_id="demo-user",
            name="Interrupted",
            prompt="Build a product catalog",
            mode="team",
            status="draft",
        )
        db.add(project)
        db.flush()
        project_session = ProjectSession(project_id=project.id, user_id="demo-user")
        db.add(project_session)
        db.flush()
        run = Run(
            project_id=project.id,
            session_id=project_session.id,
            user_id="demo-user",
            mode="team",
            model="mock",
            status="product_running",
            current_stage="product_manager",
            prompt=project.prompt,
        )
        db.add(run)
        db.flush()
        reserve_quota(db, "demo-user", run, "product_manager", 1)
        run_id = run.id
        db.commit()

    assert recover_interrupted_blueprints(session_factory) == 1
    with session_factory() as db:
        run = db.get(Run, run_id)
        user = db.get(User, "demo-user")
        assert run is not None and user is not None
        assert run.status == "build_queued"
        assert run.quota_reserved == 0
        assert run.quota_spent == 1
        assert user.quota_reserved == 0
        assert get_artifact(db, run.id, ArtifactType.BLUEPRINT) is not None
        assert (
            db.scalar(select(func.count()).select_from(BuildJob).where(BuildJob.run_id == run.id))
            == 1
        )


def test_concurrent_approval_cas_creates_one_job_and_approval(queued_client: TestClient) -> None:
    created = _create_run(queued_client, "Build a product catalog with login")
    assert created["status"] == "awaiting_approval"
    approval = BlueprintApproval(blueprint=Blueprint.model_validate(created["blueprint"]))
    session_factory = queued_client.app.state.testing_session

    def approve_once() -> str:
        with session_factory() as db:
            user = db.get(User, "demo-user")
            assert user is not None
            try:
                approve_blueprint(
                    created["run_id"],
                    approval,
                    lambda _job_id: None,
                    db,
                    user,
                )
                return "accepted"
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: approve_once(), range(2)))

    assert sorted(outcomes) == ["APPROVAL_NOT_ALLOWED", "accepted"]
    with session_factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(BuildJob)
                .where(BuildJob.run_id == created["run_id"])
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Approval)
                .where(Approval.run_id == created["run_id"])
            )
            == 1
        )


def test_completed_run_is_not_replayed_when_job_cleanup_was_interrupted(
    queued_client: TestClient,
) -> None:
    created = _create_run(queued_client)
    assert created["status"] == "build_queued"
    session_factory = queued_client.app.state.testing_session
    assert process_next_job(session_factory, worker_id="first-worker")

    with session_factory() as db:
        run = db.get(Run, created["run_id"])
        job = db.get(BuildJob, created["build_job_id"])
        assert run is not None and job is not None
        assert run.status == "completed"
        used_before = run.quota_spent
        versions_before = db.scalar(
            select(func.count()).select_from(ProjectVersion).where(ProjectVersion.run_id == run.id)
        )
        job.status = "building"
        job.lease_owner = "dead-after-commit"
        job.lease_expires_at = now_utc() - timedelta(seconds=1)
        db.commit()

    assert claim_next_job(session_factory, worker_id="replacement-worker") is None
    with session_factory() as db:
        run = db.get(Run, created["run_id"])
        job = db.get(BuildJob, created["build_job_id"])
        assert run is not None and job is not None
        assert job.status == "succeeded"
        assert run.quota_spent == used_before
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProjectVersion)
                .where(ProjectVersion.run_id == run.id)
            )
            == versions_before
            == 1
        )


def test_mid_pipeline_recovery_reuses_completed_stage_artifacts(
    queued_client: TestClient,
) -> None:
    created = _create_run(queued_client)
    assert created["status"] == "build_queued"
    session_factory = queued_client.app.state.testing_session
    claimed = claim_next_job(session_factory, worker_id="first-worker")
    assert claimed == created["build_job_id"]

    with session_factory() as db:
        run = db.get(Run, created["run_id"])
        job = db.get(BuildJob, claimed)
        blueprint_artifact = get_artifact(db, created["run_id"], ArtifactType.BLUEPRINT)
        assert run is not None and job is not None and blueprint_artifact is not None
        Orchestrator(db)._run_architect(
            run,
            Blueprint.model_validate(blueprint_artifact.payload),
        )
        job.status = "building"
        job.lease_owner = "dead-mid-stage"
        job.lease_expires_at = now_utc() - timedelta(seconds=1)
        db.commit()

    replacement = claim_next_job(session_factory, worker_id="replacement-worker")
    assert replacement == claimed
    execute_claimed_job(replacement, session_factory)

    with session_factory() as db:
        run = db.get(Run, created["run_id"])
        job = db.get(BuildJob, claimed)
        assert run is not None and job is not None
        architect_settles = db.scalar(
            select(func.count())
            .select_from(UsageLedger)
            .where(
                UsageLedger.run_id == run.id,
                UsageLedger.stage == "architect",
                UsageLedger.entry_type == "settle",
            )
        )
        assert run.status == "completed"
        assert run.quota_spent == 4
        assert job.attempt == 2
        assert architect_settles == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProjectVersion)
                .where(ProjectVersion.run_id == run.id)
            )
            == 1
        )
