from datetime import timedelta

from fastapi.testclient import TestClient

from another_atom.build.worker import claim_next_job
from another_atom.storage.models import BuildJob, Run, now_utc


def test_expired_worker_lease_can_be_reclaimed(client: TestClient) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a product catalog", "mode": "team"},
    ).json()
    approved = client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": created["blueprint"]},
    ).json()

    session_factory = client.app.state.testing_session
    with session_factory() as db:
        job = db.get(BuildJob, approved["build_job_id"])
        run = db.get(Run, created["run_id"])
        assert job is not None and run is not None
        job.status = "building"
        job.lease_owner = "dead-worker"
        job.lease_expires_at = now_utc() - timedelta(seconds=1)
        run.status = "build_queued"
        db.commit()

    claimed = claim_next_job(session_factory, worker_id="replacement-worker")
    assert claimed == approved["build_job_id"]
    with session_factory() as db:
        job = db.get(BuildJob, claimed)
        assert job is not None
        assert job.lease_owner == "replacement-worker"
        assert job.attempt == 2
