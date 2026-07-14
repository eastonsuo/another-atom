import asyncio
import socket
import threading
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from another_atom.agent.orchestrator import Orchestrator
from another_atom.config import get_settings
from another_atom.contracts.schemas import BuildStatus, ProjectStatus, RunStatus
from another_atom.domain.events import record_event
from another_atom.domain.quota import release_quota
from another_atom.observability import get_logger
from another_atom.storage.database import SessionLocal
from another_atom.storage.models import BuildJob, Project, Run, now_utc

logger = get_logger("worker")


def worker_identity() -> str:
    return f"{socket.gethostname()}-{uuid4().hex[:8]}"


def renew_job_lease(
    session_factory: sessionmaker,
    *,
    job_id: str,
    lease_owner: str,
    lease_seconds: int,
) -> bool:
    with session_factory() as db:
        result = db.execute(
            update(BuildJob)
            .where(
                BuildJob.id == job_id,
                BuildJob.lease_owner == lease_owner,
                BuildJob.status.in_(
                    [BuildStatus.BUILDING.value, BuildStatus.VALIDATING.value]
                ),
            )
            .values(lease_expires_at=now_utc() + timedelta(seconds=lease_seconds))
        )
        db.commit()
        return bool(result.rowcount)


@contextmanager
def job_lease_heartbeat(
    session_factory: sessionmaker,
    *,
    job_id: str,
    lease_owner: str | None,
):
    if not lease_owner:
        yield
        return
    settings = get_settings()
    interval = max(
        1.0,
        min(settings.worker_heartbeat_seconds, settings.worker_lease_seconds / 3),
    )
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(interval):
            try:
                if not renew_job_lease(
                    session_factory,
                    job_id=job_id,
                    lease_owner=lease_owner,
                    lease_seconds=settings.worker_lease_seconds,
                ):
                    return
            except Exception:
                logger.exception("build_job_lease_heartbeat_failed", extra={"job_id": job_id})
                return

    thread = threading.Thread(
        target=heartbeat,
        name=f"lease-heartbeat-{job_id[:8]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval + 1)


def claim_next_job(
    session_factory: sessionmaker = SessionLocal,
    *,
    worker_id: str,
) -> str | None:
    now = now_utc()
    with session_factory() as db:
        while True:
            job = db.scalar(
                select(BuildJob)
                .where(
                    or_(
                        BuildJob.status == BuildStatus.QUEUED.value,
                        (
                            BuildJob.status.in_(
                                [BuildStatus.BUILDING.value, BuildStatus.VALIDATING.value]
                            )
                            & or_(
                                BuildJob.lease_expires_at.is_(None),
                                BuildJob.lease_expires_at < now,
                            )
                        ),
                    )
                )
                .order_by(BuildJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            run = db.get(Run, job.run_id)
            if run is None or run.status in {
                RunStatus.COMPLETED.value,
                RunStatus.COMPLETED_DEGRADED.value,
                RunStatus.FAILED.value,
                RunStatus.CANCELLED.value,
                RunStatus.NEEDS_INPUT.value,
            }:
                job.status = (
                    BuildStatus.SUCCEEDED.value
                    if run
                    and run.status
                    in {RunStatus.COMPLETED.value, RunStatus.COMPLETED_DEGRADED.value}
                    else BuildStatus.WAITING_INPUT.value
                    if run and run.status == RunStatus.NEEDS_INPUT.value
                    else BuildStatus.FAILED.value
                )
                job.lease_owner = None
                job.lease_expires_at = None
                job.finished_at = job.finished_at or now
                db.commit()
                continue
            if run.quota_reserved:
                release_quota(db, run, "worker_recovery")
            job.status = BuildStatus.BUILDING.value
            job.lease_owner = worker_id
            job.lease_expires_at = now + timedelta(seconds=get_settings().worker_lease_seconds)
            job.started_at = job.started_at or now
            job.attempt += 1
            db.commit()
            logger.info(
                "build_job_claimed",
                extra={"job_id": job.id, "run_id": job.run_id, "project_id": job.project_id},
            )
            return job.id


def execute_claimed_job(
    job_id: str,
    session_factory: sessionmaker = SessionLocal,
) -> None:
    with session_factory() as db:
        job = db.get(BuildJob, job_id)
        if job is None:
            logger.warning("claimed_build_job_missing", extra={"job_id": job_id})
            return
        try:
            logger.info(
                "build_job_started",
                extra={"job_id": job.id, "run_id": job.run_id, "project_id": job.project_id},
            )
            with job_lease_heartbeat(
                session_factory,
                job_id=job.id,
                lease_owner=job.lease_owner,
            ):
                Orchestrator(db).execute_approved_run(job.run_id)
        except Exception as exc:
            logger.exception("build_job_crashed", extra={"job_id": job_id, "run_id": job.run_id})
            db.rollback()
            _fail_job(db, job_id, str(exc))
            return

        job = db.get(BuildJob, job_id)
        run = db.get(Run, job.run_id) if job else None
        if job is None:
            return
        if run is None or run.status == RunStatus.FAILED.value:
            job.status = BuildStatus.FAILED.value
        elif run.status in {
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_DEGRADED.value,
        }:
            job.status = BuildStatus.SUCCEEDED.value
        elif run.status == RunStatus.NEEDS_INPUT.value:
            job.status = BuildStatus.WAITING_INPUT.value
        job.lease_owner = None
        job.lease_expires_at = None
        job.finished_at = now_utc()
        db.commit()
        logger.info(
            "build_job_finished",
            extra={"job_id": job.id, "run_id": job.run_id, "status": job.status},
        )


def process_next_job(
    session_factory: sessionmaker = SessionLocal,
    *,
    worker_id: str | None = None,
) -> bool:
    job_id = claim_next_job(session_factory, worker_id=worker_id or worker_identity())
    if job_id is None:
        return False
    execute_claimed_job(job_id, session_factory)
    return True


def _fail_job(db: Session, job_id: str, message: str) -> None:
    job = db.get(BuildJob, job_id)
    if job is None:
        return
    logger.error("build_job_marked_failed", extra={"job_id": job_id, "run_id": job.run_id})
    run = db.get(Run, job.run_id)
    job.status = BuildStatus.FAILED.value
    job.error_message = message[:2000]
    job.lease_owner = None
    job.lease_expires_at = None
    job.finished_at = now_utc()
    if run:
        run.status = RunStatus.FAILED.value
        run.error_code = "WORKER_FAILED"
        run.error_message = message[:2000]
        release_quota(db, run, run.current_stage)
        project = db.get(Project, run.project_id)
        if project:
            project.status = (
                ProjectStatus.READY.value
                if project.latest_version_id
                else ProjectStatus.DRAFT.value
            )
            if project.active_write_run_id == run.id:
                project.active_write_run_id = None
        record_event(
            db,
            run.id,
            "run.failed",
            "The build worker stopped unexpectedly",
            stage=run.current_stage,
            payload={"code": "WORKER_FAILED"},
        )
    db.commit()


async def worker_loop(stop: asyncio.Event) -> None:
    worker_id = worker_identity()
    while not stop.is_set():
        processed = await asyncio.to_thread(process_next_job, SessionLocal, worker_id=worker_id)
        if not processed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=get_settings().worker_poll_seconds)
            except TimeoutError:
                pass
