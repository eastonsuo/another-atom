from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from another_atom.api.dependencies import get_job_dispatcher
from another_atom.build.worker import process_next_job
from another_atom.config import get_settings
from another_atom.main import create_app
from another_atom.storage.database import Base, create_database_engine, get_db


@pytest.fixture
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()
    database_path = tmp_path / "test.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with testing_session() as session:
            yield session

    def execute(_job_id: str) -> None:
        assert process_next_job(testing_session, worker_id="test-worker")

    app = create_app(initialize_database=False)
    app.state.testing_session = testing_session
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_job_dispatcher] = lambda: execute
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()
