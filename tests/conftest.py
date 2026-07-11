from collections.abc import Generator
from functools import partial

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from another_atom.agent.tasks import execute_blueprint_background
from another_atom.api.dependencies import get_blueprint_executor, get_job_dispatcher
from another_atom.build.worker import process_next_job
from another_atom.config import get_settings
from another_atom.main import create_app
from another_atom.storage.database import Base, create_database_engine, get_db


def _test_client(tmp_path, monkeypatch, *, process_jobs: bool):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    database_path = tmp_path / "test.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with testing_session() as session:
            yield session

    app = create_app(initialize_database=False)
    app.state.testing_session = testing_session
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_blueprint_executor] = lambda: partial(
        execute_blueprint_background, session_factory=testing_session
    )
    if process_jobs:
        def execute(_job_id: str) -> None:
            assert process_next_job(testing_session, worker_id="test-worker")

        app.dependency_overrides[get_job_dispatcher] = lambda: execute
    else:
        app.dependency_overrides[get_job_dispatcher] = lambda: (lambda _job_id: None)
    return app, engine


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    app, engine = _test_client(tmp_path, monkeypatch, process_jobs=True)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


@pytest.fixture
def queued_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    app, engine = _test_client(tmp_path, monkeypatch, process_jobs=False)
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()
