from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from another_atom.agent.orchestrator import Orchestrator
from another_atom.api.dependencies import get_run_executor
from another_atom.main import create_app
from another_atom.storage.database import Base, create_database_engine, get_db


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "test.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_db():
        with testing_session() as session:
            yield session

    def execute(run_id: str) -> None:
        with testing_session() as session:
            Orchestrator(session).execute_approved_run(run_id)

    app = create_app(initialize_database=False)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_run_executor] = lambda: execute
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()
