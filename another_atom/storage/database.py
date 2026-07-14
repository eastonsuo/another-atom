import re
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, or_, select, text
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
        run_additions = {
            "model": "VARCHAR(100) DEFAULT 'mock' NOT NULL",
            "trigger": "VARCHAR(24) DEFAULT 'build' NOT NULL",
            "base_version_id": "VARCHAR(36)",
        }
        for name, column_type in run_additions.items():
            if name not in run_columns:
                connection.execute(text(f"ALTER TABLE runs ADD COLUMN {name} {column_type}"))
        user_additions = {
            "username": "VARCHAR(80)",
            "password_hash": "VARCHAR(255)",
            "role": "VARCHAR(20) DEFAULT 'user' NOT NULL",
        }
        for name, column_type in user_additions.items():
            if name not in user_columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {column_type}"))
        project_additions = {
            "repository_path": "VARCHAR(500)",
            "repository_branch": "VARCHAR(80) DEFAULT 'main' NOT NULL",
            "active_write_run_id": "VARCHAR(36)",
        }
        for name, column_type in project_additions.items():
            if name not in project_columns:
                connection.execute(text(f"ALTER TABLE projects ADD COLUMN {name} {column_type}"))
        if "git_commit" not in version_columns:
            connection.execute(
                text("ALTER TABLE project_versions ADD COLUMN git_commit VARCHAR(40)")
            )
        if "data_profile" not in version_columns:
            connection.execute(text("ALTER TABLE project_versions ADD COLUMN data_profile JSON"))
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
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_human_task_run_kind_subject_idx "
                "ON human_tasks (run_id, kind, subject_hash)"
            )
        )
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_idx ON users (username)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users (role)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_runs_trigger ON runs (trigger)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_runs_base_version_id ON runs (base_version_id)")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_projects_active_write_run_id "
                "ON projects (active_write_run_id)"
            )
        )

    from another_atom.contracts.schemas import AppSpec, VersionSource
    from another_atom.domain.auth import hash_password, verify_password
    from another_atom.observability import get_logger
    from another_atom.repository.service import (
        commit_version,
        find_file_save_commit,
        initialize_repository,
        read_repository_file,
        repository_content_hash,
    )
    from another_atom.storage.models import FileSaveOperation, Project, ProjectVersion, User

    logger = get_logger("database")

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
        settings = get_settings()
        protected_environment = settings.environment not in {"development", "test"}
        if bool(settings.admin_username) != bool(settings.admin_password):
            raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD must be configured together")
        if (
            protected_environment
            and settings.admin_username == "admin"
            and settings.admin_password == "admin12345"
        ):
            # Accepted V1 boundary: the default admin stays usable in public deployments,
            # but the operator must be able to see that the well-known credentials are live.
            logger.warning(
                "default_admin_credentials_active",
                extra={"status": "warning"},
            )
        if protected_environment and not settings.session_cookie_secure:
            logger.warning(
                "session_cookie_secure_disabled",
                extra={"status": "warning"},
            )
        if settings.admin_username and settings.admin_password:
            admin_username = settings.admin_username.lower()
            if not re.fullmatch(r"[a-zA-Z0-9_-]{3,80}", admin_username):
                raise RuntimeError("ADMIN_USERNAME must satisfy the normal username contract")
            if len(settings.admin_password) < 10:
                raise RuntimeError("ADMIN_PASSWORD must contain at least 10 characters")
            admin = db.scalar(select(User).where(User.username == admin_username))
            if admin is None:
                admin = User(
                    username=admin_username,
                    display_name=settings.admin_display_name,
                    role="admin",
                    plan="internal",
                    quota_limit=0,
                    password_hash=hash_password(settings.admin_password),
                )
                db.add(admin)
            else:
                admin.role = "admin"
                admin.display_name = settings.admin_display_name
                if admin.password_hash is None or not verify_password(
                    settings.admin_password, admin.password_hash
                ):
                    admin.password_hash = hash_password(settings.admin_password)
            # The configured credentials are the only source of admin identity;
            # demote any stale admin account left behind by earlier configurations.
            leftover_admins = db.scalars(
                select(User).where(
                    User.role == "admin",
                    or_(User.username.is_(None), User.username != admin_username),
                )
            ).all()
            for leftover in leftover_admins:
                leftover.role = "user"
                logger.warning(
                    "stale_admin_demoted",
                    extra={"user_id": leftover.id, "status": "warning"},
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
        interrupted_saves = db.scalars(
            select(FileSaveOperation).where(
                FileSaveOperation.status.in_(["pending", "writing", "committed"])
            )
        ).all()
        for operation in interrupted_saves:
            try:
                git_commit = find_file_save_commit(operation.project_id, operation.id)
                if git_commit:
                    content = read_repository_file(operation.project_id, operation.path)
                    operation.git_commit = git_commit
                    operation.target_hash = repository_content_hash(content)
                    operation.status = "completed"
                    operation.error_code = None
                else:
                    operation.status = "failed"
                    operation.error_code = "REPOSITORY_FILE_SAVE_INTERRUPTED"
                project = db.get(Project, operation.project_id)
                if project and project.active_write_run_id == operation.id:
                    project.active_write_run_id = None
            except Exception:
                logger.exception(
                    "file_save_recovery_failed",
                    extra={"project_id": operation.project_id, "operation_id": operation.id},
                )
        db.commit()


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
