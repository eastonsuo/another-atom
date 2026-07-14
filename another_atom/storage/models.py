from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from another_atom.storage.database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Demo User")
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    plan: Mapped[str] = mapped_column(String(32), default="demo")
    quota_limit: Mapped[int] = mapped_column(Integer, default=100)
    quota_used: Mapped[int] = mapped_column(Integer, default=0)
    quota_reserved: Mapped[int] = mapped_column(Integer, default=0)


class AuthSession(Base, TimestampMixin):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadMessage(Base, TimestampMixin):
    __tablename__ = "lead_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(String(20))
    response: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(300))
    model: Mapped[str] = mapped_column(String(100))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)


class SandboxSession(Base, TimestampMixin):
    __tablename__ = "sandbox_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    remote_session_id: Mapped[str] = mapped_column(String(80), unique=True)
    terminal_token: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), default="Untitled project")
    prompt: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    latest_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    repository_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    repository_branch: Mapped[str] = mapped_column(String(80), default="main")
    active_write_run_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    active_turn_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    active_turn_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProjectSession(Base, TimestampMixin):
    __tablename__ = "project_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Build session")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Run(Base, TimestampMixin):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("project_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(100), default="mock")
    trigger: Mapped[str] = mapped_column(String(24), default="build", index=True)
    base_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32))
    current_stage: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quota_reserved: Mapped[int] = mapped_column(Integer, default=0)
    quota_spent: Mapped[int] = mapped_column(Integer, default=0)


class ProjectMessage(Base, TimestampMixin):
    __tablename__ = "project_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("project_sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    message_type: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FileSaveOperation(Base, TimestampMixin):
    __tablename__ = "file_save_operations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(500))
    expected_hash: Mapped[str] = mapped_column(String(71))
    target_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    git_commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_versions.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("run_id", "artifact_type", name="uq_run_artifact_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40))
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class Approval(Base, TimestampMixin):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("run_id", name="uq_approval_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id", ondelete="CASCADE"))
    approved: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class HumanTask(Base, TimestampMixin):
    __tablename__ = "human_tasks"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "kind", "subject_hash", name="uq_human_task_run_kind_subject"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text)
    subject_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class BuildJob(Base, TimestampMixin):
    __tablename__ = "build_jobs"
    __table_args__ = (UniqueConstraint("run_id", name="uq_build_job_run"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ProjectVersion(Base, TimestampMixin):
    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "version_number", name="uq_project_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(24))
    app_spec: Mapped[dict[str, Any]] = mapped_column(JSON)
    architecture_design: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_bundle: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    execution_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    build_artifact: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    data_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_report: Mapped[dict[str, Any]] = mapped_column(JSON)
    review_report: Mapped[dict[str, Any]] = mapped_column("qa_review", JSON)
    git_commit: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)


class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True
    )
    public_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    strategy: Mapped[str] = mapped_column(String(32))
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_versions.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str] = mapped_column(String(120))
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    units: Mapped[int] = mapped_column(Integer)
    entry_type: Mapped[str] = mapped_column(String(24))
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
