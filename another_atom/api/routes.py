import asyncio
import json
import re
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as websocket_connect

from another_atom.agent.provider import LLMProviderError, get_llm_provider
from another_atom.api.dependencies import (
    get_blueprint_executor,
    get_current_user,
    get_job_dispatcher,
    get_sandbox,
)
from another_atom.build.renderer import validate_app_spec
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    ArtifactType,
    AuthCredentials,
    Blueprint,
    BlueprintApproval,
    BuildStatus,
    DataProfile,
    DeploymentView,
    EventView,
    HealthView,
    LeadDecisionView,
    LeadMessageRequest,
    Mode,
    ModelOption,
    ModelsView,
    ProjectFileContent,
    ProjectFileEntry,
    ProjectStatus,
    ProjectView,
    PublicationStrategy,
    PublishRequest,
    QuotaView,
    ReviewReport,
    RevisionRequest,
    RewriteConfirmation,
    RunCreate,
    RunStatus,
    RunView,
    SandboxSessionView,
    SupportLevel,
    UserView,
    ValidationReport,
    VersionSource,
    VersionView,
)
from another_atom.domain.artifacts import get_artifact, save_artifact
from another_atom.domain.auth import (
    hash_password,
    hash_session_token,
    new_session_token,
    verify_password,
)
from another_atom.domain.errors import AppError
from another_atom.domain.events import record_event
from another_atom.observability import get_logger
from another_atom.repository.service import (
    RepositoryError,
    commit_version,
    initialize_repository,
    list_repository_files,
    read_repository_file,
)
from another_atom.sandbox.client import SandboxClient, SandboxUnavailable, get_sandbox_client
from another_atom.storage.database import SessionLocal, get_db
from another_atom.storage.models import (
    Approval,
    Artifact,
    Attachment,
    AuthSession,
    BuildJob,
    Deployment,
    LeadMessage,
    Project,
    ProjectSession,
    ProjectVersion,
    Run,
    RunEvent,
    SandboxSession,
    UsageLedger,
    User,
    now_utc,
)

router = APIRouter(prefix="/api")
logger = get_logger("routes")


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


def _create_auth_session(db: Session, user: User) -> tuple[AuthSession, str]:
    settings = get_settings()
    token = new_session_token()
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=now_utc() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(auth_session)
    return auth_session, token


def _owned_run(db: Session, run_id: str, user_id: str) -> Run:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user_id))
    if run is None:
        raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
    return run


def _owned_project(db: Session, project_id: str, user_id: str) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "Project was not found", 404)
    return project


def _artifact_model(db: Session, run_id: str, kind: ArtifactType, model):
    artifact = get_artifact(db, run_id, kind)
    return model.model_validate(artifact.payload) if artifact else None


def _coerce_review_report(payload: dict | None) -> ReviewReport | None:
    if payload is None:
        return None
    if "verdict" in payload:
        return ReviewReport.model_validate(payload)
    return ReviewReport(
        summary=str(payload.get("summary") or "Legacy review result"),
        verdict="accept",
        engineering_checks=list(payload.get("engineering_checks") or []),
        data_findings=list(payload.get("data_checks") or []),
        warnings=list(payload.get("warnings") or []),
        suggested_actions=list(payload.get("suggested_actions") or ["accept"]),
        reviewer_mode="deterministic_only",
    )


def _run_review_report(db: Session, run_id: str) -> ReviewReport | None:
    artifact = get_artifact(db, run_id, ArtifactType.REVIEW_REPORT)
    if artifact:
        return ReviewReport.model_validate(artifact.payload)
    legacy = get_artifact(db, run_id, ArtifactType.DATA_REVIEW)
    return _coerce_review_report(legacy.payload if legacy else None)


def _run_view(db: Session, run: Run) -> RunView:
    build_job = db.scalar(
        select(BuildJob)
        .where(BuildJob.run_id == run.id)
        .order_by(BuildJob.created_at.desc())
        .limit(1)
    )
    version = db.scalar(
        select(ProjectVersion)
        .where(ProjectVersion.run_id == run.id)
        .order_by(ProjectVersion.version_number.desc())
    )
    app_spec = _artifact_model(db, run.id, ArtifactType.APP_SPEC_REPAIR, AppSpec)
    if app_spec is None:
        app_spec = _artifact_model(db, run.id, ArtifactType.APP_SPEC, AppSpec)
    validation_report = _artifact_model(
        db,
        run.id,
        ArtifactType.REPAIR_VALIDATION_REPORT,
        ValidationReport,
    )
    if validation_report is None:
        validation_report = _artifact_model(
            db,
            run.id,
            ArtifactType.VALIDATION_REPORT,
            ValidationReport,
        )
    return RunView(
        run_id=run.id,
        project_id=run.project_id,
        session_id=run.session_id,
        prompt=run.prompt,
        mode=Mode(run.mode),
        model=run.model,
        status=RunStatus(run.status),
        current_stage=run.current_stage,
        blueprint=_artifact_model(db, run.id, ArtifactType.BLUEPRINT, Blueprint),
        architecture_spec=_artifact_model(
            db, run.id, ArtifactType.ARCHITECTURE_SPEC, ArchitectureSpec
        ),
        app_spec=app_spec,
        data_profile=_artifact_model(db, run.id, ArtifactType.DATA_PROFILE, DataProfile),
        validation_report=validation_report,
        review_report=_run_review_report(db, run.id),
        build_job_id=build_job.id if build_job else None,
        version_id=version.id if version else None,
        error_code=run.error_code,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _deployment_view(deployment: Deployment | None) -> DeploymentView | None:
    if deployment is None or deployment.version_id is None:
        return None
    return DeploymentView(
        public_id=deployment.public_id,
        project_id=deployment.project_id,
        version_id=deployment.version_id,
        strategy=PublicationStrategy(deployment.strategy),
        status="live" if deployment.active else "paused",
        public_url=f"{get_settings().public_base_url}/apps/{deployment.public_id}",
    )


@router.get("/health", response_model=HealthView)
def health(db: Session = Depends(get_db)) -> HealthView:
    db.scalar(select(func.count()).select_from(User))
    return HealthView(
        llm_provider=get_settings().llm_provider,
        database="postgresql" if get_settings().database_url.startswith("postgresql") else "sqlite",
    )


@router.post("/auth/signup", response_model=UserView, status_code=status.HTTP_201_CREATED)
def signup(
    credentials: AuthCredentials,
    response: Response,
    db: Session = Depends(get_db),
) -> UserView:
    username = credentials.username.lower()
    if db.scalar(select(User).where(User.username == username)) is not None:
        raise AppError("USERNAME_TAKEN", "That username is already in use", 409)
    user = User(
        username=username,
        password_hash=hash_password(credentials.password),
        display_name=credentials.display_name or credentials.username,
        plan="demo",
        quota_limit=get_settings().demo_quota_units,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError("USERNAME_TAKEN", "That username is already in use", 409) from exc
    _, token = _create_auth_session(db, user)
    db.commit()
    _set_session_cookie(response, token)
    return UserView(
        id=user.id,
        username=username,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/auth/login", response_model=UserView)
def login(
    credentials: AuthCredentials,
    response: Response,
    db: Session = Depends(get_db),
) -> UserView:
    username = credentials.username.lower()
    user = db.scalar(select(User).where(User.username == username))
    if (
        user is None
        or user.password_hash is None
        or not verify_password(credentials.password, user.password_hash)
    ):
        raise AppError("INVALID_CREDENTIALS", "Username or password is incorrect", 401)
    _, token = _create_auth_session(db, user)
    db.commit()
    _set_session_cookie(response, token)
    return UserView(
        id=user.id,
        username=username,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Response:
    session_token = request.cookies.get(get_settings().session_cookie_name)
    if session_token:
        auth_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_session_token(session_token),
                AuthSession.revoked_at.is_(None),
            )
        )
        if auth_session:
            auth_session.revoked_at = now_utc()
            db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user)) -> UserView:
    if user.username is None:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in to continue", 401)
    return UserView(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


@router.get("/quota", response_model=QuotaView)
def quota(user: User = Depends(get_current_user)) -> QuotaView:
    return QuotaView(
        limit=user.quota_limit,
        used=user.quota_used,
        reserved=user.quota_reserved,
        remaining=user.quota_limit - user.quota_used - user.quota_reserved,
    )


@router.post("/lead/messages", response_model=LeadDecisionView)
def route_lead_message(
    request: LeadMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LeadDecisionView:
    model_config = models()
    selected_model = request.model or model_config.default_model
    if selected_model not in {option.id for option in model_config.models}:
        raise AppError("MODEL_NOT_ALLOWED", "Selected model is not available", 422)
    provider = get_llm_provider(model=selected_model)
    logger.info("lead_request_started", extra={"provider": provider.name})
    reserved = provider.reservation_units
    claimed = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.quota_used + User.quota_reserved + reserved <= User.quota_limit,
        )
        .values(quota_reserved=User.quota_reserved + reserved)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("QUOTA_EXCEEDED", "Not enough quota for the Lead request", 402)
    db.commit()
    try:
        decision = provider.route_message(request.message, request.force_team)
        usage = provider.take_usage()
    except LLMProviderError as exc:
        logger.warning("lead_request_failed", extra={"provider": provider.name})
        usage = provider.take_usage()
        _settle_lead_quota(db, user.id, reserved, usage.request_count)
        db.add(
            LeadMessage(
                user_id=user.id,
                content=request.message,
                route="failed",
                response="Lead request failed",
                reason=str(exc)[:300],
                model=selected_model,
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        )
        db.commit()
        raise AppError("LEAD_FAILED", str(exc), 502) from exc
    except Exception as exc:
        logger.exception("lead_request_platform_failure", extra={"provider": provider.name})
        usage = provider.take_usage()
        _settle_lead_quota(db, user.id, reserved, usage.request_count)
        db.add(
            LeadMessage(
                user_id=user.id,
                content=request.message,
                route="failed",
                response="Lead request failed",
                reason=str(exc)[:300],
                model=selected_model,
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        )
        db.commit()
        raise AppError("LEAD_PLATFORM_FAILED", "Lead execution failed", 502) from exc
    lead_message = LeadMessage(
        user_id=user.id,
        content=request.message,
        route=decision.route.value,
        response=decision.response,
        reason=decision.reason,
        model=selected_model,
        request_count=usage.request_count,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    logger.info(
        "lead_request_completed",
        extra={"provider": provider.name, "status": decision.route.value},
    )
    db.add(lead_message)
    _settle_lead_quota(db, user.id, reserved, usage.request_count)
    db.commit()
    return LeadDecisionView(
        message_id=lead_message.id,
        model=selected_model,
        fallback_provider=usage.fallback_provider,
        **decision.model_dump(),
    )


def _settle_lead_quota(db: Session, user_id: str, reserved: int, request_count: int) -> None:
    actual = min(reserved, request_count)
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            quota_reserved=User.quota_reserved - reserved,
            quota_used=User.quota_used + actual,
        )
    )


@router.get("/models", response_model=ModelsView)
def models() -> ModelsView:
    settings = get_settings()
    sandbox_available = bool(settings.sandbox_host_url and settings.sandbox_shared_secret)
    if settings.llm_provider == "ollama":
        return ModelsView(
            provider="ollama",
            fallback_provider="deepseek" if settings.deepseek_api_key else None,
            sandbox_available=sandbox_available,
            default_model=settings.ollama_model,
            models=[
                ModelOption(id="deepseek-v4-pro", label="DeepSeek V4 Pro", usage="extra_high"),
                ModelOption(id="deepseek-v4-flash", label="DeepSeek V4 Flash", usage="medium"),
            ],
        )
    return ModelsView(
        provider="mock",
        fallback_provider=None,
        sandbox_available=sandbox_available,
        default_model="mock",
        models=[ModelOption(id="mock", label="Mock LLM", usage="local")],
    )


@router.post("/runs", response_model=RunView, status_code=status.HTTP_201_CREATED)
def create_run(
    request: RunCreate,
    background_tasks: BackgroundTasks,
    blueprint_executor: Callable[[str], None] = Depends(get_blueprint_executor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    model_config = models()
    selected_model = request.model or model_config.default_model
    if selected_model not in {option.id for option in model_config.models}:
        raise AppError("MODEL_NOT_ALLOWED", "Selected model is not available", 422)
    project = Project(
        user_id=user.id,
        name="Untitled project",
        prompt=request.prompt,
        mode=request.mode.value,
        status=ProjectStatus.DRAFT.value,
    )
    db.add(project)
    db.flush()
    try:
        project.repository_path = str(initialize_repository(project.id))
        project.repository_branch = "main"
    except RepositoryError as exc:
        logger.exception(
            "project_repository_initialization_failed",
            extra={"project_id": project.id},
        )
        db.rollback()
        raise AppError("REPOSITORY_INIT_FAILED", str(exc), 500) from exc
    project_session = ProjectSession(project_id=project.id, user_id=user.id)
    db.add(project_session)
    db.flush()
    run = Run(
        project_id=project.id,
        session_id=project_session.id,
        user_id=user.id,
        mode=request.mode.value,
        model=selected_model,
        status=RunStatus.PRODUCT_RUNNING.value,
        current_stage="product_manager",
        prompt=request.prompt,
    )
    db.add(run)
    db.flush()
    for attachment in request.attachments:
        db.add(
            Attachment(
                project_id=project.id,
                name=attachment.name,
                size=attachment.size,
                media_type=attachment.content_type,
            )
        )
    db.commit()
    logger.info(
        "run_created",
        extra={"run_id": run.id, "project_id": project.id, "status": run.status},
    )
    background_tasks.add_task(blueprint_executor, run.id)
    return _run_view(db, run)


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    return _run_view(db, _owned_run(db, run_id, user.id))


@router.post(
    "/runs/{run_id}/approve",
    response_model=RunView,
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_blueprint(
    run_id: str,
    approval: BlueprintApproval,
    job_dispatcher: Callable[[str], None] = Depends(get_job_dispatcher),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    if approval.blueprint.support_level == SupportLevel.UNSUPPORTED:
        raise AppError(
            "UNSUPPORTED_REQUEST", "Unsupported requests cannot enter the build pipeline", 409
        )
    claimed = db.execute(
        update(Run)
        .where(
            Run.id == run_id,
            Run.user_id == user.id,
            Run.status == RunStatus.AWAITING_APPROVAL.value,
        )
        .values(status=RunStatus.BUILD_QUEUED.value, current_stage="build_queue")
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        run = db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user.id))
        if run is None:
            raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
        raise AppError(
            "APPROVAL_NOT_ALLOWED", "This run is not waiting for Blueprint approval", 409
        )
    run = db.get(Run, run_id)
    if run is None:
        db.rollback()
        raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
    artifact = save_artifact(db, run.id, ArtifactType.BLUEPRINT, approval.blueprint)
    db.add(
        Approval(
            run_id=run.id,
            user_id=user.id,
            artifact_id=artifact.id,
            approved=True,
            payload=approval.blueprint.model_dump(mode="json"),
        )
    )
    job = BuildJob(run_id=run.id, project_id=run.project_id, status=BuildStatus.QUEUED.value)
    db.add(job)
    db.flush()
    record_event(
        db,
        run.id,
        "approval.confirmed",
        "Blueprint approved; build job queued",
        stage="blueprint_approval",
    )
    record_event(
        db,
        run.id,
        "build.queued",
        "Build is queued",
        stage="build_queue",
        payload={"build_job_id": job.id},
    )
    db.commit()
    job_dispatcher(job.id)
    db.refresh(run)
    return _run_view(db, run)


@router.post(
    "/runs/{run_id}/confirm-alternative",
    response_model=RunView,
    status_code=status.HTTP_202_ACCEPTED,
)
def confirm_alternative_blueprint(
    run_id: str,
    confirmation: RewriteConfirmation,
    job_dispatcher: Callable[[str], None] = Depends(get_job_dispatcher),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    source_run = _owned_run(db, run_id, user.id)
    if source_run.status != RunStatus.NEEDS_INPUT.value:
        raise AppError("ALTERNATIVE_NOT_ALLOWED", "This run is not waiting for an alternative", 409)
    source_artifact = get_artifact(db, source_run.id, ArtifactType.BLUEPRINT)
    if source_artifact is None:
        raise AppError("MISSING_INPUT", "Source Blueprint could not be loaded", 409)
    source_blueprint = Blueprint.model_validate(source_artifact.payload)
    if source_blueprint.support_level != SupportLevel.UNSUPPORTED:
        raise AppError(
            "ALTERNATIVE_NOT_ALLOWED", "Only unsupported requests use this confirmation", 409
        )
    confirmed_blueprint = source_blueprint.model_copy(
        update={
            "support_level": SupportLevel.SUPPORTED,
            "support_reasons": [
                "The user explicitly accepted the Product Manager requirement draft."
            ],
            "rewrite_suggestion": None,
        }
    )
    db.add(
        Approval(
            run_id=source_run.id,
            user_id=user.id,
            artifact_id=source_artifact.id,
            approved=True,
            payload={
                "confirmation_type": "requirement_draft",
                "confirmed_prompt": confirmation.prompt,
                "blueprint": confirmed_blueprint.model_dump(mode="json"),
            },
        )
    )
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            "ALTERNATIVE_ALREADY_CONFIRMED", "This alternative was already confirmed", 409
        ) from exc
    project_session = ProjectSession(project_id=source_run.project_id, user_id=user.id)
    db.add(project_session)
    db.flush()
    next_run = Run(
        project_id=source_run.project_id,
        session_id=project_session.id,
        user_id=user.id,
        mode=source_run.mode,
        model=source_run.model,
        status=RunStatus.BUILD_QUEUED.value,
        current_stage="build_queue",
        prompt=confirmation.prompt,
    )
    db.add(next_run)
    db.flush()
    artifact = save_artifact(db, next_run.id, ArtifactType.BLUEPRINT, confirmed_blueprint)
    job = BuildJob(
        run_id=next_run.id,
        project_id=next_run.project_id,
        status=BuildStatus.QUEUED.value,
    )
    db.add(job)
    db.flush()
    project = db.get(Project, source_run.project_id)
    if project:
        project.name = confirmed_blueprint.project_name
        project.prompt = confirmation.prompt
    record_event(
        db,
        source_run.id,
        "approval.confirmed",
        "User accepted the Product Manager requirement draft",
        stage="scope_review",
        payload={"next_run_id": next_run.id},
    )
    record_event(
        db,
        next_run.id,
        "artifact.created",
        "Confirmed Blueprint copied without another Product Manager pass",
        stage="product_manager",
        payload={"artifact_id": artifact.id, "source_run_id": source_run.id},
    )
    record_event(
        db,
        next_run.id,
        "build.queued",
        "Confirmed requirement is queued for architecture",
        stage="build_queue",
        payload={"build_job_id": job.id},
    )
    db.commit()
    job_dispatcher(job.id)
    db.refresh(next_run)
    return _run_view(db, next_run)


@router.post(
    "/runs/{run_id}/regenerate-alternative",
    response_model=RunView,
    status_code=status.HTTP_202_ACCEPTED,
)
def regenerate_alternative_blueprint(
    run_id: str,
    request: RewriteConfirmation,
    background_tasks: BackgroundTasks,
    blueprint_executor: Callable[[str], None] = Depends(get_blueprint_executor),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    source_run = _owned_run(db, run_id, user.id)
    if source_run.status != RunStatus.NEEDS_INPUT.value:
        raise AppError(
            "ALTERNATIVE_NOT_ALLOWED", "This run is not waiting for a new requirement", 409
        )
    project_session = ProjectSession(project_id=source_run.project_id, user_id=user.id)
    db.add(project_session)
    db.flush()
    next_run = Run(
        project_id=source_run.project_id,
        session_id=project_session.id,
        user_id=user.id,
        mode=source_run.mode,
        model=source_run.model,
        status=RunStatus.PRODUCT_RUNNING.value,
        current_stage="product_manager",
        prompt=request.prompt,
    )
    db.add(next_run)
    db.flush()
    project = db.get(Project, source_run.project_id)
    if project:
        project.prompt = request.prompt
    record_event(
        db,
        source_run.id,
        "alternative.regeneration_requested",
        "User asked Product Manager to regenerate the requirement draft",
        stage="scope_review",
        payload={"next_run_id": next_run.id},
    )
    record_event(
        db,
        next_run.id,
        "alternative.regeneration_requested",
        "A new requirement draft is queued for Product Manager",
        stage="product_manager",
        payload={"source_run_id": source_run.id},
    )
    db.commit()
    background_tasks.add_task(blueprint_executor, next_run.id)
    db.refresh(next_run)
    return _run_view(db, next_run)


@router.get("/runs/{run_id}/events/history", response_model=list[EventView])
def event_history(
    run_id: str,
    after: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EventView]:
    _owned_run(db, run_id, user.id)
    events = db.scalars(
        select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > after).order_by(RunEvent.id)
    ).all()
    return [_event_view(event) for event in events]


def _render_run_log(
    run: Run,
    build_job: BuildJob | None,
    artifacts: list[Artifact],
    usage_entries: list[UsageLedger],
    events: list[RunEvent],
) -> str:
    """Format all persisted Run diagnostics for a user-owned debug download."""
    lines = [
        "Another Atom debug log",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        f"Run ID: {run.id}",
        f"Project ID: {run.project_id}",
        f"Session ID: {run.session_id}",
        f"Status: {run.status}",
        f"Current stage: {run.current_stage}",
        f"Model: {run.model}",
        f"Created at: {run.created_at.isoformat()}",
        f"Updated at: {run.updated_at.isoformat()}",
        f"Error code: {run.error_code or '-'}",
        f"Error message: {run.error_message or '-'}",
        f"Quota spent: {run.quota_spent}",
        f"Quota reserved: {run.quota_reserved}",
        "",
        "Prompt:",
        run.prompt,
        "",
        "Build job:",
    ]
    if build_job is None:
        lines.append("-")
    else:
        lines.append(
            json.dumps(
                {
                    "id": build_job.id,
                    "status": build_job.status,
                    "attempt": build_job.attempt,
                    "error_message": build_job.error_message,
                    "lease_owner": build_job.lease_owner,
                    "lease_expires_at": build_job.lease_expires_at,
                    "started_at": build_job.started_at,
                    "finished_at": build_job.finished_at,
                    "log_path": build_job.log_path,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    lines.extend(["", f"Artifacts ({len(artifacts)}):"])
    for artifact in artifacts:
        lines.extend(
            [
                "",
                f"[{artifact.created_at.isoformat()}] {artifact.artifact_type}",
                f"artifact_id: {artifact.id}",
                f"schema_version: {artifact.schema_version}",
                "payload:",
                json.dumps(
                    artifact.payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            ]
        )
    lines.extend(["", f"Usage ledger ({len(usage_entries)}):"])
    for entry in usage_entries:
        lines.append(
            json.dumps(
                {
                    "id": entry.id,
                    "stage": entry.stage,
                    "entry_type": entry.entry_type,
                    "units": entry.units,
                    "request_count": entry.request_count,
                    "input_tokens": entry.input_tokens,
                    "output_tokens": entry.output_tokens,
                    "created_at": entry.created_at,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        )
    lines.extend(["", f"Events ({len(events)}):"])
    for event in events:
        lines.extend(
            [
                "",
                f"[{event.created_at.isoformat()}] #{event.id} {event.event_type}",
                f"stage: {event.stage or '-'}",
                f"message: {event.message}",
                "payload:",
                json.dumps(
                    event.payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    default=str,
                ),
            ]
        )
    return "\n".join(lines) + "\n"


@router.get("/runs/{run_id}/logs/download")
def download_run_log(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    run = _owned_run(db, run_id, user.id)
    build_job = db.scalar(
        select(BuildJob)
        .where(BuildJob.run_id == run.id)
        .order_by(BuildJob.created_at.desc())
        .limit(1)
    )
    artifacts = list(
        db.scalars(
            select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.created_at)
        ).all()
    )
    usage_entries = list(
        db.scalars(
            select(UsageLedger).where(UsageLedger.run_id == run.id).order_by(UsageLedger.created_at)
        ).all()
    )
    events = db.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id)
    ).all()
    return Response(
        content=_render_run_log(run, build_job, artifacts, usage_entries, events),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="another-atom-run-{run.id}.log"',
            "Cache-Control": "no-store",
        },
    )


def _event_view(event: RunEvent) -> EventView:
    payload = {"message": event.message, "stage": event.stage, **event.payload}
    return EventView(
        event_id=str(event.id),
        sequence=event.id,
        run_id=event.run_id,
        type=event.event_type,
        payload=payload,
        timestamp=event.created_at,
    )


@router.get("/runs/{run_id}/events")
def stream_events(
    run_id: str,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    after: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    _owned_run(db, run_id, user.id)
    cursor = max(after, int(last_event_id or 0))

    async def generate() -> AsyncIterator[str]:
        nonlocal cursor
        idle_after_terminal = 0
        with SessionLocal() as event_db:
            while True:
                event_db.expire_all()
                events = event_db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > cursor)
                    .order_by(RunEvent.id)
                ).all()
                run = event_db.get(Run, run_id)
                for event in events:
                    cursor = event.id
                    view = _event_view(event)
                    yield (
                        f"id: {event.id}\n"
                        f"event: {event.event_type}\n"
                        f"data: {view.model_dump_json()}\n\n"
                    )
                terminal = run is None or run.status in {
                    RunStatus.COMPLETED.value,
                    RunStatus.COMPLETED_DEGRADED.value,
                    RunStatus.FAILED.value,
                    RunStatus.CANCELLED.value,
                    RunStatus.NEEDS_INPUT.value,
                }
                event_db.rollback()
                if terminal and not events:
                    idle_after_terminal += 1
                    if idle_after_terminal >= 2:
                        break
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/projects", response_model=list[ProjectView])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ProjectView]:
    projects = db.scalars(
        select(Project).where(Project.user_id == user.id).order_by(Project.updated_at.desc())
    ).all()
    return [_project_view(db, project) for project in projects]


@router.get("/projects/{project_id}", response_model=ProjectView)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectView:
    return _project_view(db, _owned_project(db, project_id, user.id))


@router.get("/projects/{project_id}/runs/latest", response_model=RunView)
def latest_project_run(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    project = _owned_project(db, project_id, user.id)
    run = db.scalar(select(Run).where(Run.project_id == project.id).order_by(Run.created_at.desc()))
    if run is None:
        raise AppError("RUN_NOT_FOUND", "Project does not have a run", 404)
    return _run_view(db, run)


def _project_view(db: Session, project: Project) -> ProjectView:
    run = db.scalar(select(Run).where(Run.project_id == project.id).order_by(Run.created_at.desc()))
    blueprint = _artifact_model(db, run.id, ArtifactType.BLUEPRINT, Blueprint) if run else None
    deployment = db.scalar(select(Deployment).where(Deployment.project_id == project.id))
    return ProjectView(
        id=project.id,
        name=project.name,
        status=ProjectStatus(project.status),
        support_level=blueprint.support_level if blueprint else None,
        current_version_id=project.latest_version_id,
        deployment=_deployment_view(deployment),
        created_at=project.created_at,
        updated_at=project.updated_at,
        repository_ready=project.repository_path is not None,
        repository_branch=project.repository_branch,
    )


_ARTIFACT_FILE_PATHS = {
    ArtifactType.BLUEPRINT: ".another-atom/generated/blueprint.json",
    ArtifactType.ARCHITECTURE_SPEC: ".another-atom/generated/architecture-spec.json",
    ArtifactType.APP_SPEC: ".another-atom/generated/app-spec.json",
    ArtifactType.APP_SPEC_REPAIR: ".another-atom/generated/app-spec-repair.json",
    ArtifactType.DATA_PROFILE: ".another-atom/generated/data-profile.json",
    ArtifactType.VALIDATION_REPORT: ".another-atom/generated/validation-report.json",
    ArtifactType.REPAIR_VALIDATION_REPORT: (
        ".another-atom/generated/repair-validation-report.json"
    ),
    ArtifactType.REVIEW_REPORT: ".another-atom/generated/review-report.json",
    ArtifactType.DATA_REVIEW: ".another-atom/generated/legacy-data-review.json",
}


def _owned_project_run(db: Session, project: Project, run_id: str | None) -> Run | None:
    query = select(Run).where(Run.project_id == project.id)
    if run_id:
        query = query.where(Run.id == run_id)
    else:
        query = query.order_by(Run.created_at.desc())
    return db.scalar(query)


@router.get("/projects/{project_id}/files", response_model=list[ProjectFileEntry])
def list_project_files(
    project_id: str,
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectFileEntry]:
    project = _owned_project(db, project_id, user.id)
    try:
        files = [
            ProjectFileEntry(path=path, source="repository", size=size)
            for path, size in list_repository_files(project.id)
        ]
    except RepositoryError as exc:
        raise AppError("REPOSITORY_NOT_READY", str(exc), 409) from exc
    run = _owned_project_run(db, project, run_id)
    if run_id and run is None:
        raise AppError("RUN_NOT_FOUND", "Project Run was not found", 404)
    if run:
        artifacts = db.scalars(
            select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.created_at)
        ).all()
        for artifact in artifacts:
            artifact_type = ArtifactType(artifact.artifact_type)
            path = _ARTIFACT_FILE_PATHS.get(artifact_type)
            if path:
                content = json.dumps(artifact.payload, ensure_ascii=False, indent=2) + "\n"
                files.append(
                    ProjectFileEntry(
                        path=path,
                        source="artifact",
                        size=len(content.encode("utf-8")),
                    )
                )
    return files


@router.get("/projects/{project_id}/files/content", response_model=ProjectFileContent)
def get_project_file_content(
    project_id: str,
    path: str = Query(min_length=1, max_length=500),
    source: str = Query(pattern="^(repository|artifact)$"),
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectFileContent:
    project = _owned_project(db, project_id, user.id)
    if source == "repository":
        try:
            content = read_repository_file(project.id, path)
        except RepositoryError as exc:
            raise AppError("REPOSITORY_FILE_NOT_READABLE", str(exc), 404) from exc
        return ProjectFileContent(path=path, source="repository", content=content)

    run = _owned_project_run(db, project, run_id)
    if run is None:
        raise AppError("RUN_NOT_FOUND", "Project Run was not found", 404)
    artifact_type = next(
        (
            artifact_type
            for artifact_type, file_path in _ARTIFACT_FILE_PATHS.items()
            if file_path == path
        ),
        None,
    )
    if artifact_type is None:
        raise AppError("ARTIFACT_FILE_NOT_FOUND", "Generated artifact file was not found", 404)
    artifact = get_artifact(db, run.id, artifact_type)
    if artifact is None:
        raise AppError("ARTIFACT_FILE_NOT_FOUND", "Generated artifact file was not found", 404)
    return ProjectFileContent(
        path=path,
        source="artifact",
        content=json.dumps(artifact.payload, ensure_ascii=False, indent=2) + "\n",
    )


@router.get("/projects/{project_id}/versions", response_model=list[VersionView])
def list_versions(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VersionView]:
    _owned_project(db, project_id, user.id)
    versions = db.scalars(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project_id)
        .order_by(ProjectVersion.version_number.desc())
    ).all()
    return [_version_view(version) for version in versions]


def _version_view(version: ProjectVersion) -> VersionView:
    return VersionView(
        id=version.id,
        project_id=version.project_id,
        number=version.version_number,
        source=VersionSource(version.source),
        summary=f"{version.source.title()} version {version.version_number}",
        app_spec=AppSpec.model_validate(version.app_spec),
        created_at=version.created_at,
        git_commit=version.git_commit,
    )


@router.get("/previews/{version_id}", response_model=AppSpec)
def preview(
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AppSpec:
    version = db.scalar(
        select(ProjectVersion)
        .join(Project, Project.id == ProjectVersion.project_id)
        .where(ProjectVersion.id == version_id, Project.user_id == user.id)
    )
    if version is None:
        raise AppError("VERSION_NOT_FOUND", "Preview version was not found", 404)
    return AppSpec.model_validate(version.app_spec)


@router.post("/projects/{project_id}/revisions", response_model=VersionView)
def revise_project(
    project_id: str,
    revision: RevisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VersionView:
    project = _owned_project(db, project_id, user.id)
    current = db.get(ProjectVersion, project.latest_version_id)
    if current is None:
        raise AppError("VERSION_NOT_FOUND", "Build a version before editing", 409)
    app_spec = AppSpec.model_validate(current.app_spec)
    updates = revision.model_dump(exclude_none=True)
    if not updates:
        raise AppError("EMPTY_REVISION", "Provide at least one field to update", 422)
    if app_spec.html:
        html = app_spec.html
        css = app_spec.css
        if "hero_title" in updates:
            html = html.replace(app_spec.hero_title, updates["hero_title"])
        if "hero_body" in updates:
            html = html.replace(app_spec.hero_body, updates["hero_body"])
        if "primary_color" in updates:
            css = re.sub(
                re.escape(app_spec.primary_color),
                updates["primary_color"],
                css,
                flags=re.IGNORECASE,
            )
        updates.update({"html": html, "css": css})
    app_spec = AppSpec.model_validate(app_spec.model_copy(update=updates))
    blueprint, architecture_spec = _validation_contracts(db, current.run_id)
    validation = validate_app_spec(
        app_spec,
        project.prompt,
        blueprint=blueprint,
        architecture_spec=architecture_spec,
    )
    if not validation.passed:
        raise AppError("REVISION_VALIDATION_FAILED", "The revision failed validation", 422)
    review_report = _coerce_review_report(current.review_report)
    assert review_report is not None
    review_report = review_report.model_copy(
        update={
            "engineering_checks": [check.label for check in validation.checks],
            "reviewer_mode": "deterministic_only",
        }
    )
    latest_number = db.scalar(
        select(func.max(ProjectVersion.version_number)).where(
            ProjectVersion.project_id == project.id
        )
    )
    version = ProjectVersion(
        project_id=project.id,
        run_id=current.run_id,
        version_number=(latest_number or 0) + 1,
        source=VersionSource.EDIT.value,
        app_spec=app_spec.model_dump(mode="json"),
        data_profile=current.data_profile,
        validation_report=validation.model_dump(mode="json"),
        review_report=review_report.model_dump(mode="json"),
    )
    db.add(version)
    db.flush()
    version.git_commit = commit_version(
        project.id,
        version.id,
        version.version_number,
        VersionSource.EDIT,
        app_spec,
    )
    project.latest_version_id = version.id
    _record_project_event(
        db,
        project.id,
        "version.created",
        "A validated edit version was created",
        {"version_id": version.id, "source": VersionSource.EDIT.value},
    )
    db.commit()
    db.refresh(version)
    return _version_view(version)


@router.post("/projects/{project_id}/restore/{version_id}", response_model=VersionView)
def restore_version(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VersionView:
    project = _owned_project(db, project_id, user.id)
    source_version = db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.id == version_id, ProjectVersion.project_id == project.id
        )
    )
    if source_version is None:
        raise AppError("VERSION_NOT_FOUND", "Restore version was not found", 404)
    restored_app_spec = AppSpec.model_validate(source_version.app_spec)
    blueprint, architecture_spec = _validation_contracts(db, source_version.run_id)
    validation = validate_app_spec(
        restored_app_spec,
        project.prompt,
        blueprint=blueprint,
        architecture_spec=architecture_spec,
    )
    if not validation.passed:
        raise AppError("RESTORE_VALIDATION_FAILED", "The selected version failed validation", 422)
    latest_number = db.scalar(
        select(func.max(ProjectVersion.version_number)).where(
            ProjectVersion.project_id == project.id
        )
    )
    restored = ProjectVersion(
        project_id=project.id,
        run_id=source_version.run_id,
        version_number=(latest_number or 0) + 1,
        source=VersionSource.RESTORE.value,
        app_spec=source_version.app_spec,
        data_profile=source_version.data_profile,
        validation_report=validation.model_dump(mode="json"),
        review_report=source_version.review_report,
    )
    db.add(restored)
    db.flush()
    restored.git_commit = commit_version(
        project.id,
        restored.id,
        restored.version_number,
        VersionSource.RESTORE,
        restored_app_spec,
    )
    project.latest_version_id = restored.id
    _record_project_event(
        db,
        project.id,
        "version.restored",
        "A validated restore version was created",
        {"version_id": restored.id, "source_version_id": source_version.id},
    )
    db.commit()
    db.refresh(restored)
    return _version_view(restored)


def _validation_contracts(
    db: Session, run_id: str
) -> tuple[Blueprint | None, ArchitectureSpec | None]:
    return (
        _artifact_model(db, run_id, ArtifactType.BLUEPRINT, Blueprint),
        _artifact_model(db, run_id, ArtifactType.ARCHITECTURE_SPEC, ArchitectureSpec),
    )


def _record_project_event(
    db: Session,
    project_id: str,
    event_type: str,
    message: str,
    payload: dict,
) -> None:
    run = db.scalar(
        select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc()).limit(1)
    )
    if run:
        record_event(db, run.id, event_type, message, stage="delivery", payload=payload)


@router.post("/projects/{project_id}/publish", response_model=DeploymentView)
def publish_project(
    project_id: str,
    request: PublishRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeploymentView:
    project = _owned_project(db, project_id, user.id)
    version = db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.id == request.version_id,
            ProjectVersion.project_id == project.id,
        )
    )
    if version is None:
        raise AppError("VERSION_NOT_FOUND", "Publish version was not found", 404)
    deployment = db.scalar(select(Deployment).where(Deployment.project_id == project.id))
    if deployment is None:
        deployment = Deployment(
            project_id=project.id,
            public_id=uuid4().hex[:20],
            strategy=request.strategy.value,
            version_id=version.id,
        )
        db.add(deployment)
    else:
        deployment.strategy = request.strategy.value
        deployment.version_id = version.id
        deployment.active = True
    project.status = ProjectStatus.LIVE.value
    _record_project_event(
        db,
        project.id,
        "deployment.published",
        "A project version was published",
        {"version_id": version.id, "strategy": request.strategy.value},
    )
    db.commit()
    db.refresh(deployment)
    view = _deployment_view(deployment)
    assert view is not None
    return view


@router.post("/projects/{project_id}/unpublish", status_code=status.HTTP_204_NO_CONTENT)
def unpublish_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    project = _owned_project(db, project_id, user.id)
    deployment = db.scalar(select(Deployment).where(Deployment.project_id == project.id))
    if deployment:
        deployment.active = False
    project.status = ProjectStatus.READY.value
    _record_project_event(
        db,
        project.id,
        "deployment.unpublished",
        "The public deployment was disabled",
        {},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/public/{public_id}", response_model=AppSpec)
def public_app(public_id: str, db: Session = Depends(get_db)) -> AppSpec:
    deployment = db.scalar(
        select(Deployment).where(Deployment.public_id == public_id, Deployment.active.is_(True))
    )
    if deployment is None or deployment.version_id is None:
        raise AppError("PUBLICATION_NOT_FOUND", "Published app is not available", 404)
    version = db.get(ProjectVersion, deployment.version_id)
    if version is None:
        raise AppError("VERSION_NOT_FOUND", "Published version is not available", 404)
    return AppSpec.model_validate(version.app_spec)


@router.get("/projects/{project_id}/export")
def export_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    project = _owned_project(db, project_id, user.id)
    versions = db.scalars(
        select(ProjectVersion)
        .where(ProjectVersion.project_id == project.id)
        .order_by(ProjectVersion.version_number)
    ).all()
    return {
        "schema_version": "1.0",
        "exported_at": datetime.now(UTC).isoformat(),
        "project": {"id": project.id, "name": project.name, "mode": project.mode},
        "versions": [
            {
                "id": item.id,
                "number": item.version_number,
                "source": item.source,
                "app_spec": item.app_spec,
                "created_at": item.created_at.isoformat(),
            }
            for item in versions
        ],
    }


@router.post(
    "/projects/{project_id}/sandbox/sessions",
    response_model=SandboxSessionView,
    status_code=status.HTTP_201_CREATED,
)
def create_project_sandbox(
    project_id: str,
    sandbox_factory: Callable[[], SandboxClient] = Depends(get_sandbox),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SandboxSessionView:
    project = _owned_project(db, project_id, user.id)
    if project.latest_version_id is None or project.repository_path is None:
        raise AppError("SANDBOX_NOT_READY", "Build a Project version before opening Vim", 409)
    sandbox = sandbox_factory()
    try:
        remote = sandbox.create(project.id)
    except SandboxUnavailable as exc:
        raise AppError("SANDBOX_UNAVAILABLE", str(exc), 503) from exc
    session = SandboxSession(
        user_id=user.id,
        project_id=project.id,
        remote_session_id=remote.session_id,
        terminal_token=remote.terminal_token,
        expires_at=remote.expires_at,
    )
    db.add(session)
    db.commit()
    return SandboxSessionView(
        session_id=session.id,
        project_id=project.id,
        websocket_path=f"/api/sandbox/sessions/{session.id}/terminal",
        expires_at=session.expires_at,
    )


@router.delete(
    "/projects/{project_id}/sandbox/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def close_project_sandbox(
    project_id: str,
    session_id: str,
    sandbox_factory: Callable[[], SandboxClient] = Depends(get_sandbox),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    project = _owned_project(db, project_id, user.id)
    session = _owned_sandbox_session(db, session_id, user.id)
    if session.project_id != project.id:
        raise AppError("SANDBOX_SESSION_NOT_FOUND", "Sandbox session was not found", 404)
    claimed = db.execute(
        update(SandboxSession)
        .where(
            SandboxSession.id == session.id,
            SandboxSession.status == "open",
            SandboxSession.closed_at.is_(None),
        )
        .values(status="closing")
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("SANDBOX_CLOSE_NOT_ALLOWED", "Sandbox session is busy", 409)
    db.commit()
    try:
        sandbox_factory().close(session.remote_session_id)
    except SandboxUnavailable as exc:
        db.execute(
            update(SandboxSession)
            .where(
                SandboxSession.id == session.id,
                SandboxSession.status == "closing",
            )
            .values(status="open")
        )
        db.commit()
        raise AppError("SANDBOX_CLEANUP_FAILED", str(exc), 503) from exc
    db.execute(
        update(SandboxSession)
        .where(
            SandboxSession.id == session.id,
            SandboxSession.status == "closing",
        )
        .values(status="closed", closed_at=now_utc())
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _owned_sandbox_session(db: Session, session_id: str, user_id: str) -> SandboxSession:
    session = db.scalar(
        select(SandboxSession).where(
            SandboxSession.id == session_id,
            SandboxSession.user_id == user_id,
        )
    )
    expires_at = session.expires_at if session is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if session is None or session.closed_at is not None or expires_at <= now_utc():
        raise AppError("SANDBOX_SESSION_NOT_FOUND", "Sandbox session was not found", 404)
    return session


def _claim_sandbox_save(db: Session, session: SandboxSession) -> None:
    claimed = db.execute(
        update(SandboxSession)
        .where(
            SandboxSession.id == session.id,
            SandboxSession.status == "open",
            SandboxSession.closed_at.is_(None),
            SandboxSession.expires_at > now_utc(),
        )
        .values(status="saving")
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("SANDBOX_SAVE_NOT_ALLOWED", "Sandbox save is already in progress", 409)
    db.commit()


def _release_sandbox_save(db: Session, session_id: str) -> None:
    db.rollback()
    db.execute(
        update(SandboxSession)
        .where(
            SandboxSession.id == session_id,
            SandboxSession.status == "saving",
            SandboxSession.closed_at.is_(None),
        )
        .values(status="open")
    )
    db.commit()


@router.post(
    "/projects/{project_id}/sandbox/sessions/{session_id}/save",
    response_model=VersionView,
)
def save_project_sandbox(
    project_id: str,
    session_id: str,
    sandbox_factory: Callable[[], SandboxClient] = Depends(get_sandbox),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VersionView:
    project = _owned_project(db, project_id, user.id)
    session = _owned_sandbox_session(db, session_id, user.id)
    if session.project_id != project.id:
        raise AppError("SANDBOX_SESSION_NOT_FOUND", "Sandbox session was not found", 404)
    sandbox = sandbox_factory()
    _claim_sandbox_save(db, session)
    try:
        app_spec = sandbox.read_app_spec(session.remote_session_id)
    except SandboxUnavailable as exc:
        _release_sandbox_save(db, session.id)
        raise AppError("SANDBOX_UNAVAILABLE", str(exc), 503) from exc
    except Exception:
        _release_sandbox_save(db, session.id)
        raise
    try:
        current = db.get(ProjectVersion, project.latest_version_id)
        if current is None:
            raise AppError("VERSION_NOT_FOUND", "Build a version before saving Vim changes", 409)
        blueprint, architecture_spec = _validation_contracts(db, current.run_id)
        validation = validate_app_spec(
            app_spec,
            project.prompt,
            blueprint=blueprint,
            architecture_spec=architecture_spec,
        )
        if not validation.passed:
            raise AppError("SANDBOX_VALIDATION_FAILED", "The edited AppSpec failed validation", 422)
        latest_number = db.scalar(
            select(func.max(ProjectVersion.version_number)).where(
                ProjectVersion.project_id == project.id
            )
        )
        version = ProjectVersion(
            project_id=project.id,
            run_id=current.run_id,
            version_number=(latest_number or 0) + 1,
            source=VersionSource.EDIT.value,
            app_spec=app_spec.model_dump(mode="json"),
            data_profile=current.data_profile,
            validation_report=validation.model_dump(mode="json"),
            review_report=current.review_report,
        )
        db.add(version)
        db.flush()
        version.git_commit = commit_version(
            project.id,
            version.id,
            version.version_number,
            VersionSource.EDIT,
            app_spec,
        )
        project.latest_version_id = version.id
        session = db.get(SandboxSession, session.id)
        assert session is not None
        session.status = "closed"
        session.closed_at = now_utc()
        _record_project_event(
            db,
            project.id,
            "version.created",
            "A validated Vim edit version was created",
            {"version_id": version.id, "source": "vim"},
        )
        db.commit()
    except Exception:
        _release_sandbox_save(db, session.id)
        raise
    try:
        sandbox.close(session.remote_session_id)
    except SandboxUnavailable:
        pass
    return _version_view(version)


def _websocket_user(websocket: WebSocket, db: Session) -> User | None:
    settings = get_settings()
    token = websocket.cookies.get(settings.session_cookie_name)
    if token:
        auth_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_session_token(token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now_utc(),
            )
        )
        if auth_session:
            return db.get(User, auth_session.user_id)
    if settings.environment == "test":
        return db.get(User, websocket.headers.get("X-User-ID", "demo-user"))
    return None


@router.websocket("/sandbox/sessions/{session_id}/terminal")
async def proxy_sandbox_terminal(websocket: WebSocket, session_id: str) -> None:
    with SessionLocal() as db:
        user = _websocket_user(websocket, db)
        if user is None:
            await websocket.close(code=4401)
            return
        try:
            session = _owned_sandbox_session(db, session_id, user.id)
            if session.status != "open":
                raise AppError("SANDBOX_SESSION_NOT_FOUND", "Sandbox session was not found", 404)
            sandbox = get_sandbox_client()
        except AppError:
            await websocket.close(code=4404)
            return
        remote_url = sandbox.websocket_url(
            session.remote_session_id,
            session.terminal_token,
        )
    await websocket.accept()
    try:
        async with websocket_connect(remote_url, max_size=1_000_000) as remote:

            async def browser_to_host() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("bytes") is not None:
                        await remote.send(message["bytes"])
                    elif message.get("text") is not None:
                        await remote.send(message["text"])

            async def host_to_browser() -> None:
                async for message in remote:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(browser_to_host(), host_to_browser())
    except (WebSocketDisconnect, OSError):
        return
