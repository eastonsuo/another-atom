from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from another_atom.agent.orchestrator import Orchestrator
from another_atom.contracts.schemas import RunStatus
from another_atom.domain.quota import release_quota
from another_atom.storage.database import SessionLocal
from another_atom.storage.models import Run


def execute_blueprint_background(
    run_id: str,
    session_factory: sessionmaker = SessionLocal,
    job_dispatcher: Callable[[str], None] | None = None,
) -> None:
    """Generate a Blueprint after the create-run transaction is committed."""
    job_id: str | None = None
    with session_factory() as db:
        run = db.get(Run, run_id)
        if run is None:
            return
        Orchestrator(db).create_blueprint(run)
        db.expire_all()
        run = db.get(Run, run_id)
        if run and run.status == RunStatus.BUILD_QUEUED.value:
            from another_atom.storage.models import BuildJob

            job = db.scalar(select(BuildJob).where(BuildJob.run_id == run_id))
            job_id = job.id if job else None
    if job_id and job_dispatcher:
        job_dispatcher(job_id)


def recover_interrupted_blueprints(session_factory: sessionmaker = SessionLocal) -> int:
    """Replay Product Manager work left in-flight by a previous process."""
    with session_factory() as db:
        run_ids = list(
            db.scalars(select(Run.id).where(Run.status == RunStatus.PRODUCT_RUNNING.value)).all()
        )
        for run_id in run_ids:
            run = db.get(Run, run_id)
            if run and run.quota_reserved:
                release_quota(db, run, "blueprint_recovery")
        db.commit()
    for run_id in run_ids:
        execute_blueprint_background(run_id, session_factory)
    return len(run_ids)
