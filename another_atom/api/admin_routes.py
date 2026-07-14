import re
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from another_atom.api.dependencies import get_current_admin
from another_atom.api.routes import _render_run_log
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AdminProjectDetail,
    AdminProjectList,
    AdminProjectSummary,
    AdminRunSummary,
    AdminUserList,
    AdminUserRoleUpdate,
    AdminUserSummary,
    AdminUserView,
    ArtifactType,
    AuthCredentials,
    Blueprint,
    EventView,
)
from another_atom.domain.auth import (
    hash_session_token,
    new_session_token,
    verify_password,
)
from another_atom.domain.errors import AppError
from another_atom.observability import get_logger
from another_atom.storage.database import get_db
from another_atom.storage.models import (
    Artifact,
    AuthSession,
    BuildJob,
    Project,
    Run,
    RunEvent,
    UsageLedger,
    User,
    now_utc,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = get_logger("admin")

# V1 runs as a single instance, so an in-process failure window is an acceptable
# brute-force guard; a shared store is only needed once there are multiple replicas.
ADMIN_LOGIN_WINDOW_SECONDS = 900
ADMIN_LOGIN_MAX_FAILURES = 5
_login_failures: dict[str, list[float]] = {}


def _prune_login_failures(username: str, now: float) -> list[float]:
    window_start = now - ADMIN_LOGIN_WINDOW_SECONDS
    failures = [moment for moment in _login_failures.get(username, []) if moment > window_start]
    if failures:
        _login_failures[username] = failures
    else:
        _login_failures.pop(username, None)
    return failures


def _register_login_failure(username: str, reason: str) -> None:
    now = time.monotonic()
    failures = _prune_login_failures(username, now)
    failures.append(now)
    _login_failures[username] = failures
    logger.warning(
        "admin_login_failed",
        extra={"resource_id": username, "status": reason},
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def _admin_user(db: Session, user_id: str) -> User:
    user = db.scalar(
        select(User).where(User.id == user_id, User.username.is_not(None), User.role == "user")
    )
    if user is None:
        raise AppError("USER_NOT_FOUND", "User was not found", 404)
    return user


def _admin_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "Project was not found", 404)
    return project


def _latest_runs(db: Session, project_ids: list[str]) -> dict[str, Run]:
    if not project_ids:
        return {}
    row_number = (
        func.row_number()
        .over(partition_by=Run.project_id, order_by=(Run.created_at.desc(), Run.id.desc()))
        .label("row_number")
    )
    ranked = select(Run.id, row_number).where(Run.project_id.in_(project_ids)).subquery()
    runs = db.scalars(
        select(Run).join(ranked, Run.id == ranked.c.id).where(ranked.c.row_number == 1)
    ).all()
    return {run.project_id: run for run in runs}


def _project_blueprints(db: Session, project_ids: list[str]) -> dict[str, Blueprint]:
    """Latest persisted Blueprint per project, regardless of whether the newest run has one."""
    if not project_ids:
        return {}
    artifacts = db.execute(
        select(Artifact, Run.project_id)
        .join(Run, Run.id == Artifact.run_id)
        .where(
            Run.project_id.in_(project_ids),
            Artifact.artifact_type == ArtifactType.BLUEPRINT.value,
        )
        .order_by(Artifact.created_at.desc(), Artifact.id.desc())
    ).all()
    result: dict[str, Blueprint] = {}
    for artifact, project_id in artifacts:
        if project_id in result:
            continue
        try:
            result[project_id] = Blueprint.model_validate(artifact.payload)
        except ValueError:
            continue
    return result


def _short_text(value: str | None, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    if not cleaned:
        return ""
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1]}…"


def _project_summary(
    project: Project,
    run: Run | None,
    blueprint: Blueprint | None,
) -> AdminProjectSummary:
    if blueprint:
        features = "、".join(blueprint.modules[:3])
        summary = f"{blueprint.product_type}：{features}" if features else blueprint.product_type
        support_level = blueprint.support_level.value
    else:
        summary = _short_text(project.prompt, 80) or "暂无简介"
        support_level = None
    latest_run = None
    if run:
        latest_run = AdminRunSummary(
            id=run.id,
            model=run.model,
            status=run.status,
            current_stage=run.current_stage,
            error_code=run.error_code,
            error_summary=_short_text(run.error_message, 240) or None,
            quota_spent=run.quota_spent,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
    return AdminProjectSummary(
        id=project.id,
        name=project.name,
        summary=_short_text(summary, 120),
        status=project.status,
        updated_at=project.updated_at,
        support_level=support_level,
        latest_run=latest_run,
    )


def _event_view(event: RunEvent) -> EventView:
    return EventView(
        event_id=str(event.id),
        sequence=event.id,
        run_id=event.run_id,
        type=event.event_type,
        payload={"message": event.message, "stage": event.stage, **event.payload},
        timestamp=event.created_at,
    )


@router.post("/login", response_model=AdminUserView)
def admin_login(
    credentials: AuthCredentials,
    response: Response,
    db: Session = Depends(get_db),
) -> AdminUserView:
    _no_store(response)
    username = credentials.username.lower()
    if len(_prune_login_failures(username, time.monotonic())) >= ADMIN_LOGIN_MAX_FAILURES:
        raise AppError(
            "ADMIN_LOGIN_LOCKED",
            "Too many failed sign-in attempts; try again later",
            429,
        )
    user = db.scalar(select(User).where(User.username == username))
    if (
        user is None
        or user.password_hash is None
        or not verify_password(credentials.password, user.password_hash)
    ):
        _register_login_failure(username, "invalid_credentials")
        raise AppError("INVALID_CREDENTIALS", "Username or password is incorrect", 401)
    if user.role != "admin":
        _register_login_failure(username, "not_admin")
        raise AppError("ADMIN_ACCESS_REQUIRED", "Administrator access is required", 403)
    _login_failures.pop(username, None)
    token = new_session_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=now_utc() + timedelta(hours=get_settings().session_ttl_hours),
        )
    )
    db.commit()
    _set_session_cookie(response, token)
    logger.info("admin_login_completed", extra={"user_id": user.id, "status": "success"})
    return AdminUserView(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name,
    )


@router.get("/me", response_model=AdminUserView)
def admin_me(
    response: Response,
    admin: User = Depends(get_current_admin),
) -> AdminUserView:
    _no_store(response)
    return AdminUserView(
        id=admin.id,
        username=admin.username or "",
        display_name=admin.display_name,
    )


@router.get("/users", response_model=AdminUserList)
def list_users(
    response: Response,
    query: str = Query(default="", max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminUserList:
    _no_store(response)
    filters = [User.username.is_not(None), User.role == "user"]
    normalized = query.strip().lower()
    if normalized:
        escaped = re.sub(r"([\\%_])", r"\\\1", normalized)
        pattern = f"%{escaped}%"
        filters.append(
            or_(
                func.lower(User.username).like(pattern, escape="\\"),
                func.lower(User.display_name).like(pattern, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    users = db.scalars(
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    user_ids = [user.id for user in users]
    counts = {
        user_id: count
        for user_id, count in db.execute(
            select(Project.user_id, func.count(Project.id))
            .where(Project.user_id.in_(user_ids))
            .group_by(Project.user_id)
        ).all()
    } if user_ids else {}
    logger.info("admin_users_viewed", extra={"user_id": admin.id, "status": "success"})
    return AdminUserList(
        items=[
            AdminUserSummary(
                id=user.id,
                username=user.username or "",
                display_name=user.display_name,
                plan=user.plan,
                quota_limit=user.quota_limit,
                quota_used=user.quota_used,
                quota_reserved=user.quota_reserved,
                project_count=counts.get(user.id, 0),
                created_at=user.created_at,
            )
            for user in users
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserView)
def update_user_role(
    user_id: str,
    role_update: AdminUserRoleUpdate,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminUserView:
    _no_store(response)
    user = _admin_user(db, user_id)
    user.role = role_update.role
    db.commit()
    logger.info(
        "admin_user_role_updated",
        extra={
            "user_id": admin.id,
            "resource_id": user.id,
            "status": role_update.role,
        },
    )
    return AdminUserView(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name,
    )


@router.get("/users/{user_id}/projects", response_model=AdminProjectList)
def list_user_projects(
    user_id: str,
    response: Response,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminProjectList:
    _no_store(response)
    _admin_user(db, user_id)
    total = db.scalar(
        select(func.count()).select_from(Project).where(Project.user_id == user_id)
    ) or 0
    projects = db.scalars(
        select(Project)
        .where(Project.user_id == user_id)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    latest_runs = _latest_runs(db, [project.id for project in projects])
    blueprints = _project_blueprints(db, [project.id for project in projects])
    logger.info(
        "admin_user_projects_viewed",
        extra={"user_id": admin.id, "resource_id": user_id, "status": "success"},
    )
    return AdminProjectList(
        items=[
            _project_summary(project, latest_runs.get(project.id), blueprints.get(project.id))
            for project in projects
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/projects/{project_id}", response_model=AdminProjectDetail)
def project_detail(
    project_id: str,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminProjectDetail:
    _no_store(response)
    project = _admin_project(db, project_id)
    latest_run = _latest_runs(db, [project.id]).get(project.id)
    blueprint = _project_blueprints(db, [project.id]).get(project.id)
    events = (
        db.scalars(
            select(RunEvent).where(RunEvent.run_id == latest_run.id).order_by(RunEvent.id)
        ).all()
        if latest_run
        else []
    )
    logger.info(
        "admin_project_viewed",
        extra={"user_id": admin.id, "resource_id": project.id, "status": "success"},
    )
    return AdminProjectDetail(
        project=_project_summary(project, latest_run, blueprint),
        prompt_summary=_short_text(project.prompt, 500),
        events=[_event_view(event) for event in events],
    )


@router.get("/runs/{run_id}/logs/download")
def download_admin_run_log(
    run_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> Response:
    run = db.get(Run, run_id)
    if run is None:
        raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
    build_job = db.scalar(
        select(BuildJob)
        .where(BuildJob.run_id == run.id)
        .order_by(BuildJob.created_at.desc())
        .limit(1)
    )
    artifacts = list(
        db.scalars(select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.created_at))
    )
    usage_entries = list(
        db.scalars(
            select(UsageLedger)
            .where(UsageLedger.run_id == run.id)
            .order_by(UsageLedger.created_at)
        )
    )
    events = list(
        db.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id))
    )
    logger.info(
        "admin_run_log_downloaded",
        extra={"user_id": admin.id, "resource_id": run.id, "status": "success"},
    )
    return Response(
        content=_render_run_log(run, build_job, artifacts, usage_entries, events),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="another-atom-run-{run.id}.log"',
            "Cache-Control": "no-store",
        },
    )
