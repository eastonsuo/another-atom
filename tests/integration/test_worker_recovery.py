from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from another_atom.agent.orchestrator import Orchestrator
from another_atom.agent.tasks import recover_interrupted_blueprints
from another_atom.api.routes import approve_blueprint, respond_to_human_task
from another_atom.build.worker import (
    claim_next_job,
    execute_claimed_job,
    process_next_job,
    renew_job_lease,
)
from another_atom.contracts.schemas import (
    ArtifactType,
    Blueprint,
    BlueprintApproval,
    HumanTaskResponse,
    ProductSpec,
)
from another_atom.domain.artifacts import get_artifact
from another_atom.domain.errors import AppError
from another_atom.domain.quota import reserve_quota
from another_atom.storage.models import (
    Approval,
    BuildJob,
    HumanTask,
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
    run = client.get(f"/api/runs/{initial['run_id']}").json()
    if (
        run["status"] == "awaiting_approval"
        and run["blueprint"]["support_level"] == "supported"
    ):
        approved = client.post(
            f"/api/runs/{run['run_id']}/approve",
            json={"blueprint": run["blueprint"]},
        )
        assert approved.status_code == 202, approved.text
        run = client.get(f"/api/runs/{initial['run_id']}").json()
    return run


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


def test_worker_lease_heartbeat_only_renews_current_owner(
    queued_client: TestClient,
) -> None:
    created = _create_run(queued_client)
    session_factory = queued_client.app.state.testing_session
    job_id = claim_next_job(session_factory, worker_id="active-worker")
    assert job_id == created["build_job_id"]
    with session_factory() as db:
        job = db.get(BuildJob, job_id)
        assert job is not None and job.lease_expires_at is not None
        original_expiry = job.lease_expires_at

    assert renew_job_lease(
        session_factory,
        job_id=job_id,
        lease_owner="active-worker",
        lease_seconds=600,
    )
    assert not renew_job_lease(
        session_factory,
        job_id=job_id,
        lease_owner="stale-worker",
        lease_seconds=600,
    )
    with session_factory() as db:
        job = db.get(BuildJob, job_id)
        assert job is not None and job.lease_expires_at is not None
        assert job.lease_owner == "active-worker"
        assert job.lease_expires_at >= original_expiry


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
        assert run.status == "awaiting_approval"
        assert run.quota_reserved == 0
        assert run.quota_spent == 1
        assert user.quota_reserved == 0
        assert get_artifact(db, run.id, ArtifactType.BLUEPRINT) is not None
        assert (
            db.scalar(select(func.count()).select_from(BuildJob).where(BuildJob.run_id == run.id))
            == 0
        )


def test_ai_edit_clarification_resume_is_left_to_build_worker_recovery(
    queued_client: TestClient,
) -> None:
    initial = _create_run(queued_client, "Build a minesweeper game")
    assert initial["status"] == "build_queued"
    assert process_next_job(
        queued_client.app.state.testing_session, worker_id="initial-worker"
    )
    completed = queued_client.get(f"/api/runs/{initial['run_id']}").json()
    proposal = queued_client.post(
        f"/api/projects/{completed['project_id']}/messages",
        json={
            "message": "改一下 [lead:propose] [pm:clarify]",
            "model": "mock",
        },
    ).json()
    assert proposal["intent"] == "propose_change"
    change = queued_client.post(
        f"/api/projects/{completed['project_id']}/change-proposals/"
        f"{proposal['proposal_id']}/approve"
    ).json()
    assert change["status"] == "build_queued"
    assert process_next_job(
        queued_client.app.state.testing_session, worker_id="clarification-worker"
    )
    paused = queued_client.get(f"/api/runs/{change['run_id']}").json()
    assert paused["status"] == "needs_input"
    task = paused["pending_human_task"]

    resumed = queued_client.post(
        f"/api/human-tasks/{task['id']}/respond",
        json={"response": "Change the title and keep all existing behavior"},
    ).json()
    assert resumed["status"] == "product_running"
    assert resumed["trigger"] == "ai_edit"

    assert recover_interrupted_blueprints(queued_client.app.state.testing_session) == 0
    with queued_client.app.state.testing_session() as db:
        assert get_artifact(db, resumed["run_id"], ArtifactType.CHANGE_BRIEF) is None
        assert get_artifact(db, resumed["run_id"], ArtifactType.BLUEPRINT) is None

    assert process_next_job(
        queued_client.app.state.testing_session, worker_id="recovery-worker"
    )
    recovered = queued_client.get(f"/api/runs/{resumed['run_id']}").json()
    assert recovered["status"] == "completed"
    assert recovered["trigger"] == "ai_edit"


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


def test_concurrent_approve_and_reject_leave_one_consistent_decision(
    queued_client: TestClient,
) -> None:
    created = _create_run(queued_client, "Build a product catalog with login")
    assert created["status"] == "awaiting_approval"
    task_id = created["pending_human_task"]["id"]
    approval = BlueprintApproval(blueprint=Blueprint.model_validate(created["blueprint"]))
    session_factory = queued_client.app.state.testing_session

    def decide(decision: str) -> str:
        with session_factory() as db:
            user = db.get(User, "demo-user")
            assert user is not None
            try:
                if decision == "approve":
                    approve_blueprint(
                        created["run_id"], approval, lambda _job_id: None, db, user
                    )
                else:
                    respond_to_human_task(
                        task_id,
                        HumanTaskResponse(decision="reject"),
                        BackgroundTasks(),
                        lambda _run_id: None,
                        lambda _job_id: None,
                        db,
                        user,
                    )
                return decision
            except AppError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, ["approve", "reject"]))

    assert len({outcome for outcome in outcomes if outcome in {"approve", "reject"}}) == 1
    with session_factory() as db:
        run = db.get(Run, created["run_id"])
        task = db.get(HumanTask, task_id)
        jobs = db.scalar(
            select(func.count()).select_from(BuildJob).where(BuildJob.run_id == created["run_id"])
        )
        approvals = db.scalar(
            select(func.count()).select_from(Approval).where(Approval.run_id == created["run_id"])
        )
        assert run is not None and task is not None
        if task.status == "approved":
            assert run.status == "build_queued"
            assert jobs == approvals == 1
        else:
            assert task.status == "rejected"
            assert run.status == "cancelled"
            assert jobs == approvals == 0


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
        product_spec_artifact = get_artifact(
            db, created["run_id"], ArtifactType.PRODUCT_SPEC
        )
        assert (
            run is not None
            and job is not None
            and blueprint_artifact is not None
            and product_spec_artifact is not None
        )
        Orchestrator(db)._run_architect(
            run,
            Blueprint.model_validate(blueprint_artifact.payload),
            ProductSpec.model_validate(product_spec_artifact.payload),
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
        assert run.quota_spent == 3
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
