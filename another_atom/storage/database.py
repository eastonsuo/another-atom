from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from another_atom.config import get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


engine = create_database_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_database(target_engine: Engine | None = None) -> None:
    from another_atom.storage import models  # noqa: F401

    database_engine = target_engine or engine
    Base.metadata.create_all(bind=database_engine)
    database_inspector = inspect(database_engine)
    run_columns = {column["name"] for column in database_inspector.get_columns("runs")}
    build_columns = {column["name"] for column in database_inspector.get_columns("build_jobs")}
    ledger_columns = {column["name"] for column in database_inspector.get_columns("usage_ledger")}
    with database_engine.begin() as connection:
        if "model" not in run_columns:
            connection.execute(
                text("ALTER TABLE runs ADD COLUMN model VARCHAR(100) DEFAULT 'mock' NOT NULL")
            )
        build_additions = {
            "lease_owner": "VARCHAR(120)",
            "lease_expires_at": "TIMESTAMP",
            "started_at": "TIMESTAMP",
            "finished_at": "TIMESTAMP",
            "log_path": "VARCHAR(500)",
        }
        for name, column_type in build_additions.items():
            if name not in build_columns:
                connection.execute(text(f"ALTER TABLE build_jobs ADD COLUMN {name} {column_type}"))
        ledger_additions = {
            "request_count": "INTEGER DEFAULT 0 NOT NULL",
            "input_tokens": "INTEGER DEFAULT 0 NOT NULL",
            "output_tokens": "INTEGER DEFAULT 0 NOT NULL",
        }
        for name, column_type in ledger_additions.items():
            if name not in ledger_columns:
                connection.execute(
                    text(f"ALTER TABLE usage_ledger ADD COLUMN {name} {column_type}")
                )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_build_job_run_idx ON build_jobs (run_id)")
        )


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
