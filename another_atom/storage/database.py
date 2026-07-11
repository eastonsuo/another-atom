from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, select, text
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
    user_columns = {column["name"] for column in database_inspector.get_columns("users")}
    project_columns = {column["name"] for column in database_inspector.get_columns("projects")}
    version_columns = {
        column["name"] for column in database_inspector.get_columns("project_versions")
    }
    sandbox_columns = {
        column["name"] for column in database_inspector.get_columns("sandbox_sessions")
    }
    with database_engine.begin() as connection:
        if "model" not in run_columns:
            connection.execute(
                text("ALTER TABLE runs ADD COLUMN model VARCHAR(100) DEFAULT 'mock' NOT NULL")
            )
        user_additions = {
            "username": "VARCHAR(80)",
            "password_hash": "VARCHAR(255)",
        }
        for name, column_type in user_additions.items():
            if name not in user_columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {column_type}"))
        project_additions = {
            "repository_path": "VARCHAR(500)",
            "repository_branch": "VARCHAR(80) DEFAULT 'main' NOT NULL",
        }
        for name, column_type in project_additions.items():
            if name not in project_columns:
                connection.execute(text(f"ALTER TABLE projects ADD COLUMN {name} {column_type}"))
        if "git_commit" not in version_columns:
            connection.execute(
                text("ALTER TABLE project_versions ADD COLUMN git_commit VARCHAR(40)")
            )
        if "status" not in sandbox_columns:
            connection.execute(
                text("ALTER TABLE sandbox_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'open'")
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
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_run_idx ON approvals (run_id)")
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_idx ON users (username)")
        )

    from another_atom.contracts.schemas import AppSpec, VersionSource
    from another_atom.repository.service import commit_version, initialize_repository
    from another_atom.storage.models import Project, ProjectVersion, User

    bootstrap_session = sessionmaker(bind=database_engine, expire_on_commit=False)
    with bootstrap_session() as db:
        if db.get(User, "demo-user") is None:
            db.add(
                User(
                    id="demo-user",
                    display_name="Demo User",
                    plan="demo",
                    quota_limit=get_settings().demo_quota_units,
                )
            )
            db.commit()
        projects = db.scalars(select(Project).order_by(Project.created_at)).all()
        for project in projects:
            if project.repository_path is not None:
                continue
            project.repository_path = str(initialize_repository(project.id))
            project.repository_branch = "main"
            versions = db.scalars(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project.id)
                .order_by(ProjectVersion.version_number)
            ).all()
            for version in versions:
                version.git_commit = commit_version(
                    project.id,
                    version.id,
                    version.version_number,
                    VersionSource(version.source),
                    AppSpec.model_validate(version.app_spec),
                )
        db.commit()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
