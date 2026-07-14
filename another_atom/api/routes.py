import asyncio
import hashlib
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
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as websocket_connect

from another_atom.agent.orchestrator import Orchestrator, render_product_spec
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
    ArchitectureDesign,
    ArchitectureSpec,
    ArtifactType,
    AuthCredentials,
    Blueprint,
    BlueprintApproval,
    BuildStatus,
    DataProfile,
    DeploymentView,
    EngineerOutput,
    EventView,
    ExecutionReport,
    ExecutionRequest,
    ExecutionResult,
    HealthView,
    HumanTaskKind,
    HumanTaskResponse,
    HumanTaskStatus,
    HumanTaskView,
    LeadDecisionView,
    LeadMessageRequest,
    Mode,
    ModelOption,
    ModelsView,
    ProductSpec,
    ProductSpecUpdateRequest,
    ProjectFileContent,
    ProjectFileEntry,
    ProjectFileSaveRequest,
    ProjectFileSaveResult,
    ProjectLeadIntent,
    ProjectMessageRequest,
    ProjectMessageResult,
    ProjectMessageView,
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
    SourceBundle,
    SourceFileDraft,
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
    build_source_context,
    build_source_snapshot,
    commit_version,
    initialize_repository,
    list_repository_files,
    read_repository_file,
    repository_content_hash,
    repository_file_capabilities,
    save_repository_text_file,
    write_product_spec,
)
from another_atom.runtime.artifacts import create_source_bundle
from another_atom.runtime.client import RuntimeExecutorError, execute_request
from another_atom.sandbox.client import SandboxClient, SandboxUnavailable, get_sandbox_client
from another_atom.storage.database import SessionLocal, get_db
from another_atom.storage.models import (
    Approval,
    Artifact,
    Attachment,
    AuthSession,
    BuildJob,
    Deployment,
    FileSaveOperation,
    HumanTask,
    LeadMessage,
    Project,
    ProjectMessage,
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
    pending_human_task = db.scalar(
        select(HumanTask)
        .where(
            HumanTask.run_id == run.id,
            HumanTask.status == HumanTaskStatus.PENDING.value,
        )
        .order_by(HumanTask.created_at.desc(), HumanTask.id.desc())
        .limit(1)
    )
    return RunView(
        run_id=run.id,
        project_id=run.project_id,
        session_id=run.session_id,
        prompt=run.prompt,
        mode=Mode(run.mode),
        model=run.model,
        trigger=run.trigger,
        base_version_id=run.base_version_id,
        status=RunStatus(run.status),
        current_stage=run.current_stage,
        blueprint=_artifact_model(db, run.id, ArtifactType.BLUEPRINT, Blueprint),
        product_spec=_artifact_model(db, run.id, ArtifactType.PRODUCT_SPEC, ProductSpec),
        architecture_design=_artifact_model(
            db, run.id, ArtifactType.ARCHITECTURE_DESIGN, ArchitectureDesign
        ),
        architecture_spec=_artifact_model(
            db, run.id, ArtifactType.ARCHITECTURE_SPEC, ArchitectureSpec
        ),
        app_spec=app_spec,
        source_bundle=_artifact_model(
            db, run.id, ArtifactType.SOURCE_BUNDLE, SourceBundle
        ),
        execution_report=_artifact_model(
            db, run.id, ArtifactType.EXECUTION_REPORT, ExecutionReport
        ),
        data_profile=_artifact_model(db, run.id, ArtifactType.DATA_PROFILE, DataProfile),
        validation_report=validation_report,
        review_report=_run_review_report(db, run.id),
        build_job_id=build_job.id if build_job else None,
        version_id=version.id if version else None,
        error_code=run.error_code,
        error_message=run.error_message,
        pending_human_task=(
            _human_task_view(pending_human_task) if pending_human_task else None
        ),
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _human_task_view(task: HumanTask) -> HumanTaskView:
    return HumanTaskView(
        id=task.id,
        project_id=task.project_id,
        run_id=task.run_id,
        kind=HumanTaskKind(task.kind),
        status=HumanTaskStatus(task.status),
        stage=task.stage,
        prompt=task.prompt,
        payload=task.payload,
        response=task.response,
        created_at=task.created_at,
        resolved_at=task.resolved_at,
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
        .where(User.id == user.id)
        .values(quota_reserved=User.quota_reserved + reserved)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("USER_NOT_FOUND", "User does not exist", 404)
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
    db.add(
        ProjectMessage(
            project_id=project.id,
            session_id=project_session.id,
            user_id=user.id,
            run_id=run.id,
            role="user",
            message_type="request",
            content=request.prompt,
            payload={"request_type": "initial_build"},
        )
    )
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


@router.post("/runs/{run_id}/product-spec", response_model=RunView)
def update_product_spec(
    run_id: str,
    request: ProductSpecUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    run = _owned_run(db, run_id, user.id)
    if run.status != RunStatus.AWAITING_APPROVAL.value:
        raise AppError(
            "PRODUCT_SPEC_UPDATE_NOT_ALLOWED",
            "This run is not waiting for ProductSpec approval",
            409,
        )
    blueprint = _artifact_model(db, run.id, ArtifactType.BLUEPRINT, Blueprint)
    current_product_spec = _artifact_model(
        db,
        run.id,
        ArtifactType.PRODUCT_SPEC,
        ProductSpec,
    )
    if blueprint is None or current_product_spec is None:
        raise AppError("PRODUCT_SPEC_NOT_FOUND", "Product specification was not found", 404)

    if request.action == "regenerate":
        instruction = request.instruction or (
            f"将当前方案摘要修改为：{request.summary}" if request.summary else ""
        )
        try:
            Orchestrator(db).regenerate_product_spec(
                run,
                instruction,
                current_product_spec,
            )
        except AppError:
            raise
        except (LLMProviderError, ValueError) as exc:
            raise AppError("PRODUCT_SPEC_REGENERATION_FAILED", str(exc), 502) from exc
        db.commit()
        db.refresh(run)
        return _run_view(db, run)

    try:
        content = read_repository_file(run.project_id, "docs/product-spec.md")
    except RepositoryError as exc:
        raise AppError("PRODUCT_SPEC_NOT_FOUND", str(exc), 404) from exc

    summary = " ".join((request.summary or "").split())

    product_spec = ProductSpec(
        summary=summary,
        content=content,
        content_hash=repository_content_hash(content),
    )
    artifact = save_artifact(db, run.id, ArtifactType.PRODUCT_SPEC, product_spec)
    pending_task = db.scalar(
        select(HumanTask).where(
            HumanTask.run_id == run.id,
            HumanTask.user_id == user.id,
            HumanTask.kind == HumanTaskKind.APPROVAL.value,
            HumanTask.status == HumanTaskStatus.PENDING.value,
        )
    )
    if pending_task is not None:
        subject = f"product_spec:{artifact.id}:{product_spec.content_hash}:{product_spec.summary}"
        pending_task.subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        pending_task.payload = {
            **pending_task.payload,
            "artifact_id": artifact.id,
            "path": product_spec.path,
            "content_hash": product_spec.content_hash,
        }
    record_event(
        db,
        run.id,
        "product_spec.updated",
        "Product specification summary was updated",
        stage="blueprint_approval",
        payload={"artifact_id": artifact.id, "content_hash": product_spec.content_hash},
    )
    db.commit()
    db.refresh(run)
    return _run_view(db, run)


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
    pending_task = db.scalar(
        select(HumanTask).where(
            HumanTask.run_id == run_id,
            HumanTask.user_id == user.id,
            HumanTask.kind == HumanTaskKind.APPROVAL.value,
            HumanTask.status == HumanTaskStatus.PENDING.value,
        )
    )
    if pending_task is None:
        raise AppError(
            "APPROVAL_NOT_ALLOWED", "This run is not waiting for Blueprint approval", 409
        )
    task_claimed = db.execute(
        update(HumanTask)
        .where(
            HumanTask.id == pending_task.id,
            HumanTask.user_id == user.id,
            HumanTask.status == HumanTaskStatus.PENDING.value,
        )
        .values(
            status=HumanTaskStatus.APPROVED.value,
            response={"decision": "approve"},
            resolved_at=now_utc(),
        )
        .execution_options(synchronize_session=False)
    )
    if task_claimed.rowcount != 1:
        db.rollback()
        raise AppError(
            "APPROVAL_NOT_ALLOWED", "This run is not waiting for Blueprint approval", 409
        )
    run_claimed = db.execute(
        update(Run)
        .where(
            Run.id == run_id,
            Run.user_id == user.id,
            Run.status == RunStatus.AWAITING_APPROVAL.value,
        )
        .values(status=RunStatus.BUILD_QUEUED.value, current_stage="build_queue")
        .execution_options(synchronize_session=False)
    )
    if run_claimed.rowcount != 1:
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
    product_spec_artifact = get_artifact(db, run.id, ArtifactType.PRODUCT_SPEC)
    approved_artifact = product_spec_artifact or artifact
    approved_payload = (
        product_spec_artifact.payload
        if product_spec_artifact
        else approval.blueprint.model_dump(mode="json")
    )
    approval_record = db.scalar(select(Approval).where(Approval.run_id == run.id))
    if approval_record is None:
        db.add(
            Approval(
                run_id=run.id,
                user_id=user.id,
                artifact_id=approved_artifact.id,
                approved=True,
                payload=approved_payload,
            )
        )
    else:
        previous_payload = dict(approval_record.payload or {})
        previous_history = previous_payload.pop("_previous_approvals", [])
        approval_record.artifact_id = approved_artifact.id
        approval_record.approved = True
        approval_record.payload = {
            **approved_payload,
            "_previous_approvals": [*previous_history, previous_payload],
        }
    job = db.scalar(select(BuildJob).where(BuildJob.run_id == run.id))
    if job is None:
        job = BuildJob(
            run_id=run.id,
            project_id=run.project_id,
            status=BuildStatus.QUEUED.value,
        )
        db.add(job)
    else:
        job.status = BuildStatus.QUEUED.value
        job.error_message = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.started_at = None
        job.finished_at = None
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
    product_spec = render_product_spec(confirmation.prompt, confirmed_blueprint)
    write_product_spec(next_run.project_id, product_spec.content)
    product_spec_artifact = save_artifact(
        db, next_run.id, ArtifactType.PRODUCT_SPEC, product_spec
    )
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
        payload={
            "artifact_id": artifact.id,
            "product_spec_artifact_id": product_spec_artifact.id,
            "source_run_id": source_run.id,
        },
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


def _project_message_view(message: ProjectMessage) -> ProjectMessageView:
    return ProjectMessageView(
        id=message.id,
        project_id=message.project_id,
        run_id=message.run_id,
        role=message.role,
        message_type=message.message_type,
        content=message.content,
        payload=message.payload,
        created_at=message.created_at,
    )


def _release_project_turn(db: Session, project_id: str, turn_id: str) -> None:
    try:
        db.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.active_turn_id == turn_id,
            )
            .values(active_turn_id=None, active_turn_started_at=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "project_turn_release_failed",
            extra={"project_id": project_id, "turn_id": turn_id},
        )


@router.get(
    "/runs/{run_id}/human-tasks",
    response_model=list[HumanTaskView],
)
def list_run_human_tasks(
    run_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[HumanTaskView]:
    run = _owned_run(db, run_id, user.id)
    tasks = db.scalars(
        select(HumanTask)
        .where(HumanTask.run_id == run.id, HumanTask.user_id == user.id)
        .order_by(HumanTask.created_at, HumanTask.id)
    ).all()
    return [_human_task_view(task) for task in tasks]


@router.post(
    "/human-tasks/{task_id}/respond",
    response_model=RunView,
    status_code=status.HTTP_202_ACCEPTED,
)
def respond_to_human_task(
    task_id: str,
    response: HumanTaskResponse,
    background_tasks: BackgroundTasks,
    blueprint_executor: Callable[[str], None] = Depends(get_blueprint_executor),
    job_dispatcher: Callable[[str], None] = Depends(get_job_dispatcher),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    task = db.scalar(
        select(HumanTask).where(HumanTask.id == task_id, HumanTask.user_id == user.id)
    )
    if task is None:
        raise AppError("HUMAN_TASK_NOT_FOUND", "Human task was not found", 404)
    run = _owned_run(db, task.run_id, user.id)
    project = _owned_project(db, task.project_id, user.id)

    if task.status != HumanTaskStatus.PENDING.value:
        if (
            task.kind == HumanTaskKind.INPUT_REQUEST.value
            and task.status == HumanTaskStatus.ANSWERED.value
            and response.response
            and (task.response or {}).get("text") == response.response
        ):
            if (
                run.status == RunStatus.PRODUCT_RUNNING.value
                and run.current_stage == "product_manager"
            ):
                if run.trigger == "ai_edit":
                    job = db.scalar(
                        select(BuildJob).where(
                            BuildJob.run_id == run.id,
                            BuildJob.status == BuildStatus.QUEUED.value,
                        )
                    )
                    if job is not None:
                        job_dispatcher(job.id)
                        db.expire_all()
                        run = _owned_run(db, task.run_id, user.id)
                else:
                    background_tasks.add_task(blueprint_executor, run.id)
            return _run_view(db, run)
        raise AppError("HUMAN_TASK_ALREADY_RESOLVED", "Human task was already resolved", 409)

    if task.kind == HumanTaskKind.INPUT_REQUEST.value:
        if run.status != RunStatus.NEEDS_INPUT.value:
            raise AppError(
                "HUMAN_TASK_RUN_NOT_WAITING",
                "This run is no longer waiting for clarification",
                409,
            )
        if not response.response or response.decision is not None:
            raise AppError(
                "HUMAN_TASK_RESPONSE_REQUIRED",
                "This task needs a text response",
                422,
            )
        base_version_id = (task.payload or {}).get("base_version_id")
        if base_version_id and project.latest_version_id != base_version_id:
            stale_claimed = db.execute(
                update(HumanTask)
                .where(
                    HumanTask.id == task.id,
                    HumanTask.user_id == user.id,
                    HumanTask.status == HumanTaskStatus.PENDING.value,
                )
                .values(status=HumanTaskStatus.STALE.value, resolved_at=now_utc())
                .execution_options(synchronize_session=False)
            )
            run_cancelled = db.execute(
                update(Run)
                .where(
                    Run.id == run.id,
                    Run.user_id == user.id,
                    Run.status == RunStatus.NEEDS_INPUT.value,
                )
                .values(
                    status=RunStatus.CANCELLED.value,
                    error_code="BASE_VERSION_CHANGED",
                    error_message=(
                        "The clarification expired because the Project base version changed"
                    ),
                )
                .execution_options(synchronize_session=False)
            )
            if stale_claimed.rowcount != 1 or run_cancelled.rowcount != 1:
                db.rollback()
                raise AppError(
                    "HUMAN_TASK_ALREADY_RESOLVED", "Human task was already resolved", 409
                )
            db.add(
                ProjectMessage(
                    project_id=project.id,
                    session_id=run.session_id,
                    user_id=user.id,
                    run_id=run.id,
                    role="system",
                    message_type="error",
                    content=(
                        "The clarification expired because the Project changed. "
                        "Send the change again from the current version."
                    ),
                    payload={
                        "human_task_id": task.id,
                        "code": "BASE_VERSION_CHANGED",
                        "base_version_id": base_version_id,
                        "latest_version_id": project.latest_version_id,
                    },
                )
            )
            record_event(
                db,
                run.id,
                "human_task.stale",
                "Clarification expired because the Project base version changed",
                stage="product_manager_clarification",
                payload={"human_task_id": task.id, "code": "BASE_VERSION_CHANGED"},
            )
            db.commit()
            raise AppError(
                "BASE_VERSION_CHANGED",
                "The Project changed while waiting for clarification",
                409,
            )
        claimed = db.execute(
            update(HumanTask)
            .where(
                HumanTask.id == task.id,
                HumanTask.user_id == user.id,
                HumanTask.status == HumanTaskStatus.PENDING.value,
            )
            .values(
                status=HumanTaskStatus.ANSWERED.value,
                response={"text": response.response},
                resolved_at=now_utc(),
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise AppError(
                "HUMAN_TASK_ALREADY_RESOLVED", "Human task was already resolved", 409
            )
        db.add(
            ProjectMessage(
                project_id=project.id,
                session_id=run.session_id,
                user_id=user.id,
                run_id=run.id,
                role="user",
                message_type="clarification_response",
                content=response.response,
                payload={"human_task_id": task.id},
            )
        )
        missing_fields = (task.payload or {}).get("missing_fields", [])
        if "product_boundary_reapproval" in missing_fields:
            db.execute(
                delete(Artifact).where(
                    Artifact.run_id == run.id,
                    Artifact.artifact_type.in_(
                        [
                            ArtifactType.BLUEPRINT.value,
                            ArtifactType.ARCHITECTURE_SPEC.value,
                            ArtifactType.ARCHITECTURE_DESIGN.value,
                        ]
                    ),
                )
            )
            record_event(
                db,
                run.id,
                "architecture.product_reapproval_answered",
                "Architecture boundary feedback will be folded into a new ProductSpec",
                stage="product_manager_clarification",
                payload={"human_task_id": task.id},
            )
        run.status = RunStatus.PRODUCT_RUNNING.value
        run.current_stage = "product_manager"
        run.error_code = None
        run.error_message = None
        record_event(
            db,
            run.id,
            "human_task.answered",
            "User supplied the requested Product Manager clarification",
            stage="product_manager_clarification",
            payload={"human_task_id": task.id},
        )

        if run.trigger == "ai_edit":
            acquired = db.execute(
                update(Project)
                .where(
                    Project.id == project.id,
                    Project.user_id == user.id,
                    Project.latest_version_id == run.base_version_id,
                    Project.active_write_run_id.is_(None),
                )
                .values(
                    active_write_run_id=run.id,
                    status=ProjectStatus.BUILDING.value,
                )
                .execution_options(synchronize_session=False)
            )
            if acquired.rowcount != 1:
                db.rollback()
                raise AppError(
                    "PROJECT_WRITE_BUSY",
                    "Another change is already writing this Project",
                    409,
                )
            job = db.scalar(select(BuildJob).where(BuildJob.run_id == run.id))
            if job is None:
                job = BuildJob(
                    run_id=run.id,
                    project_id=run.project_id,
                    status=BuildStatus.QUEUED.value,
                )
                db.add(job)
                db.flush()
            else:
                job.status = BuildStatus.QUEUED.value
                job.error_message = None
                job.lease_owner = None
                job.lease_expires_at = None
                job.finished_at = None
            db.commit()
            job_dispatcher(job.id)
        else:
            db.commit()
            background_tasks.add_task(blueprint_executor, run.id)
        db.refresh(run)
        return _run_view(db, run)

    if response.decision not in {"reject", "cancel"}:
        raise AppError(
            "APPROVAL_DECISION_REQUIRED",
            "Approve the Blueprint from its review card, or reject this task",
            422,
        )
    if run.status != RunStatus.AWAITING_APPROVAL.value:
        raise AppError(
            "HUMAN_TASK_RUN_NOT_WAITING",
            "This run is no longer waiting for approval",
            409,
        )
    target_status = (
        HumanTaskStatus.REJECTED.value
        if response.decision == "reject"
        else HumanTaskStatus.CANCELLED.value
    )
    claimed = db.execute(
        update(HumanTask)
        .where(
            HumanTask.id == task.id,
            HumanTask.user_id == user.id,
            HumanTask.status == HumanTaskStatus.PENDING.value,
        )
        .values(
            status=target_status,
            response={"decision": response.decision},
            resolved_at=now_utc(),
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("HUMAN_TASK_ALREADY_RESOLVED", "Human task was already resolved", 409)
    run_cancelled = db.execute(
        update(Run)
        .where(
            Run.id == run.id,
            Run.user_id == user.id,
            Run.status == RunStatus.AWAITING_APPROVAL.value,
        )
        .values(status=RunStatus.CANCELLED.value)
        .execution_options(synchronize_session=False)
    )
    if run_cancelled.rowcount != 1:
        db.rollback()
        raise AppError("HUMAN_TASK_ALREADY_RESOLVED", "Human task was already resolved", 409)
    db.refresh(run)
    project.status = (
        ProjectStatus.READY.value if project.latest_version_id else ProjectStatus.DRAFT.value
    )
    if project.active_write_run_id == run.id:
        project.active_write_run_id = None
    record_event(
        db,
        run.id,
        "human_task.rejected",
        "User declined the pending approval",
        stage=task.stage,
        payload={"human_task_id": task.id, "decision": response.decision},
    )
    db.commit()
    return _run_view(db, run)


@router.get(
    "/projects/{project_id}/messages",
    response_model=list[ProjectMessageView],
)
def list_project_messages(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ProjectMessageView]:
    project = _owned_project(db, project_id, user.id)
    messages = db.scalars(
        select(ProjectMessage)
        .where(ProjectMessage.project_id == project.id)
        .order_by(ProjectMessage.created_at, ProjectMessage.id)
    ).all()
    return [_project_message_view(message) for message in messages]


def _project_context_snapshot(
    db: Session,
    project: Project,
    request_message: str,
    selected_files: list[str],
) -> dict:
    base_version = (
        db.get(ProjectVersion, project.latest_version_id)
        if project.latest_version_id
        else None
    )
    base_run = db.get(Run, base_version.run_id) if base_version else None
    latest_project_run = db.scalar(
        select(Run)
        .where(Run.project_id == project.id)
        .order_by(Run.created_at.desc())
    )
    context_run = base_run or latest_project_run
    blueprint = (
        _artifact_model(db, context_run.id, ArtifactType.BLUEPRINT, Blueprint)
        if context_run
        else None
    )
    product_spec = (
        _artifact_model(db, context_run.id, ArtifactType.PRODUCT_SPEC, ProductSpec)
        if context_run
        else None
    )
    architecture_spec = (
        _artifact_model(
            db,
            context_run.id,
            ArtifactType.ARCHITECTURE_SPEC,
            ArchitectureSpec,
        )
        if context_run
        else None
    )
    app_spec = AppSpec.model_validate(base_version.app_spec) if base_version else None
    deployment = db.scalar(select(Deployment).where(Deployment.project_id == project.id))
    project_messages = db.scalars(
        select(ProjectMessage)
        .where(ProjectMessage.project_id == project.id)
        .order_by(ProjectMessage.created_at, ProjectMessage.id)
    ).all()
    source_context = None
    source_error = None
    if base_version and base_version.git_commit:
        try:
            source_snapshot = build_source_snapshot(
                project.id,
                base_version.id,
                base_version.git_commit,
            )
            source_context = build_source_context(
                source_snapshot,
                request_message,
                get_settings().max_source_chars,
                selected_files,
            )
        except RepositoryError as exc:
            source_error = str(exc)
    latest_failed_run = (
        latest_project_run
        if latest_project_run and latest_project_run.status == RunStatus.FAILED.value
        else None
    )
    snapshot = {
        "schema_version": "1.0",
        "project_id": project.id,
        "project_name": project.name,
        "project_status": project.status,
        "current_version": (
            {
                "id": base_version.id,
                "number": base_version.version_number,
                "git_commit": base_version.git_commit,
            }
            if base_version
            else None
        ),
        "published_version_id": deployment.version_id if deployment and deployment.active else None,
        "product_spec": product_spec.model_dump(mode="json") if product_spec else None,
        "blueprint": blueprint.model_dump(mode="json") if blueprint else None,
        "architecture_spec": (
            architecture_spec.model_dump(mode="json") if architecture_spec else None
        ),
        "application": (
            app_spec.model_dump(
                mode="json",
                exclude={"html", "css", "javascript"},
            )
            if app_spec
            else None
        ),
        "source_context": source_context.model_dump(mode="json") if source_context else None,
        "source_context_error": source_error,
        "conversation": [
            {
                "role": message.role,
                "message_type": message.message_type,
                "content": message.content,
            }
            for message in project_messages
        ],
        "selected_files": selected_files,
        "latest_failure": (
            {
                "run_id": latest_failed_run.id,
                "stage": latest_failed_run.current_stage,
                "error_code": latest_failed_run.error_code,
                "error_message": latest_failed_run.error_message,
            }
            if latest_failed_run
            else None
        ),
    }
    snapshot["context_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return snapshot


def _project_context_manifest(snapshot: dict) -> dict:
    source_context = snapshot.get("source_context") or {}
    return {
        "context_hash": snapshot["context_hash"],
        "document_contracts": [
            key
            for key in ("product_spec", "blueprint", "architecture_spec", "application")
            if snapshot.get(key) is not None
        ],
        "conversation_message_count": len(snapshot.get("conversation") or []),
        "source_manifest_hash": source_context.get("source_manifest_hash"),
        "max_source_chars": source_context.get("max_source_chars"),
        "used_source_chars": source_context.get("used_source_chars"),
        "included_files": [
            {"path": item["path"], "sha256": item["sha256"]}
            for item in source_context.get("included_files", [])
        ],
        "omitted_files": source_context.get("omitted_files", []),
        "trimming_applied": source_context.get("trimming_applied", False),
        "source_context_error": snapshot.get("source_context_error"),
    }


@router.post(
    "/projects/{project_id}/messages",
    response_model=ProjectMessageResult,
)
def send_project_message(
    project_id: str,
    request: ProjectMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMessageResult:
    project = _owned_project(db, project_id, user.id)
    terminal_statuses = {
        RunStatus.COMPLETED.value,
        RunStatus.COMPLETED_DEGRADED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    }
    active_run = db.scalar(
        select(Run)
        .where(
            Run.project_id == project.id,
            Run.user_id == user.id,
            Run.status.notin_(terminal_statuses),
        )
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(1)
    )
    if active_run is not None:
        if active_run.status == RunStatus.NEEDS_INPUT.value:
            raise AppError(
                "PROJECT_INPUT_REQUIRED",
                "Reply to the pending Product Manager question before starting another turn",
                409,
            )
        if active_run.status == RunStatus.AWAITING_APPROVAL.value:
            raise AppError(
                "PROJECT_APPROVAL_PENDING",
                "Review or revise the pending ProductSpec before starting another turn",
                409,
            )
        raise AppError(
            "PROJECT_CONVERSATION_BUSY",
            "The current Agent turn is still running",
            409,
        )
    model_config = models()
    base_version = (
        db.get(ProjectVersion, project.latest_version_id)
        if project.latest_version_id
        else None
    )
    base_run = db.get(Run, base_version.run_id) if base_version else None
    selected_model = request.model or (base_run.model if base_run else model_config.default_model)
    if selected_model not in {option.id for option in model_config.models}:
        raise AppError("MODEL_NOT_ALLOWED", "Selected model is not available", 422)
    turn_id = str(uuid4())
    stale_before = now_utc() - timedelta(
        seconds=max(get_settings().agent_stage_timeout_seconds + 60, 600)
    )
    turn_claimed = db.execute(
        update(Project)
        .where(
            Project.id == project.id,
            Project.user_id == user.id,
            or_(
                Project.active_turn_id.is_(None),
                Project.active_turn_started_at < stale_before,
            ),
        )
        .values(active_turn_id=turn_id, active_turn_started_at=now_utc())
        .execution_options(synchronize_session=False)
    )
    if turn_claimed.rowcount != 1:
        db.rollback()
        raise AppError(
            "PROJECT_CONVERSATION_BUSY",
            "Another Project conversation turn is still running",
            409,
        )
    db.commit()
    try:
        project_session = ProjectSession(
            project_id=project.id,
            user_id=user.id,
            title="Project conversation",
        )
        db.add(project_session)
        db.flush()
        user_message = ProjectMessage(
            project_id=project.id,
            session_id=project_session.id,
            user_id=user.id,
            run_id=None,
            role="user",
            message_type="request",
            content=request.message,
            payload={
                "selected_files": request.selected_files,
                "model": selected_model,
                "client_message_id": request.client_message_id,
            },
        )
        db.add(user_message)
        db.flush()
        db.commit()
        context = _project_context_snapshot(
            db,
            project,
            request.message,
            request.selected_files,
        )
        lead_message = ProjectMessage(
            project_id=project.id,
            session_id=project_session.id,
            user_id=user.id,
            run_id=None,
            role="lead",
            message_type="agent_update",
            content="",
            payload={
                "status": "streaming",
                "model": selected_model,
                "model_output": "",
            },
        )
        db.add(lead_message)
        db.flush()
        db.commit()
        provider = get_llm_provider(model=selected_model)
        reserved = provider.reservation_units
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(quota_reserved=User.quota_reserved + reserved)
        )
        db.commit()
    except Exception:
        db.rollback()
        _release_project_turn(db, project.id, turn_id)
        raise

    active_provider_message_id: str | None = None

    def persist_project_lead_stream(event_type: str, payload: dict) -> None:
        nonlocal active_provider_message_id
        if event_type not in {
            "agent.message.started",
            "agent.message.delta",
            "agent.message.completed",
            "agent.message.failed",
            "agent.output.delta",
        }:
            return
        streamed = db.get(ProjectMessage, lead_message.id)
        if streamed is None:
            return
        next_payload = dict(streamed.payload or {})
        if event_type == "agent.message.started":
            incoming_message_id = payload.get("message_id")
            if isinstance(incoming_message_id, str):
                if (
                    active_provider_message_id
                    and incoming_message_id != active_provider_message_id
                ):
                    current_output = next_payload.get("model_output")
                    next_payload["model_output"] = (
                        f"{current_output if isinstance(current_output, str) else ''}"
                        "\n\n--- provider retry ---\n"
                    )
                    streamed.content = ""
                active_provider_message_id = incoming_message_id
            next_payload["status"] = "streaming"
        elif event_type == "agent.message.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                streamed.content = f"{streamed.content}{delta}"
        elif event_type == "agent.output.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                current_output = next_payload.get("model_output")
                next_payload["model_output"] = (
                    f"{current_output if isinstance(current_output, str) else ''}{delta}"
                )
        elif event_type == "agent.message.completed":
            next_payload["status"] = "completed"
        else:
            next_payload["status"] = "failed"
            if payload.get("reason"):
                next_payload["reason"] = payload["reason"]
        streamed.payload = next_payload
        db.commit()

    provider.begin_stage(
        timeout_seconds=get_settings().ollama_lead_timeout_seconds,
        event_handler=persist_project_lead_stream,
    )
    try:
        decision = provider.route_project_message(request.message, context, stream=True)
        usage = provider.take_usage()
    except (LLMProviderError, ValueError) as exc:
        usage = provider.take_usage()
        _settle_lead_quota(db, user.id, reserved, usage.request_count)
        error_message = ProjectMessage(
            project_id=project.id,
            session_id=project_session.id,
            user_id=user.id,
            role="system",
            message_type="error",
            content="项目对话处理失败，请重试。",
            payload={"error_code": "PROJECT_LEAD_FAILED"},
        )
        db.add(error_message)
        db.commit()
        _release_project_turn(db, project.id, turn_id)
        raise AppError("PROJECT_LEAD_FAILED", str(exc), 502) from exc
    except Exception as exc:
        logger.exception(
            "project_lead_platform_failure",
            extra={"project_id": project.id, "provider": provider.name},
        )
        usage = provider.take_usage()
        _settle_lead_quota(db, user.id, reserved, usage.request_count)
        db.add(
            ProjectMessage(
                project_id=project.id,
                session_id=project_session.id,
                user_id=user.id,
                role="system",
                message_type="error",
                content="项目对话处理失败，请重试。",
                payload={"error_code": "PROJECT_LEAD_PLATFORM_FAILED"},
            )
        )
        db.commit()
        _release_project_turn(db, project.id, turn_id)
        raise AppError(
            "PROJECT_LEAD_PLATFORM_FAILED",
            "Project conversation failed",
            502,
        ) from exc
    finally:
        provider.end_stage()

    message_type = {
        ProjectLeadIntent.ANSWER: "answer",
        ProjectLeadIntent.CLARIFY: "clarification",
        ProjectLeadIntent.PROPOSE_CHANGE: "change_proposal",
    }[decision.intent]
    context_manifest = _project_context_manifest(context)
    payload = {
        "reason": decision.reason,
        "model": selected_model,
        **context_manifest,
    }
    if decision.intent == ProjectLeadIntent.PROPOSE_CHANGE:
        payload.update(
            {
                "status": "pending",
                "change_summary": decision.change_summary,
                "request_message_id": user_message.id,
                "base_version_id": base_version.id if base_version else None,
                "base_git_commit": base_version.git_commit if base_version else None,
                "selected_files": request.selected_files,
            }
        )
    streamed_payload = dict(lead_message.payload or {})
    lead_message.message_type = message_type
    lead_message.content = decision.response
    lead_message.payload = {
        **streamed_payload,
        **payload,
        "status": payload.get("status", "completed"),
    }
    db.add_all(
        [
            LeadMessage(
                user_id=user.id,
                content=request.message,
                route=f"project_{decision.intent.value}",
                response=decision.response,
                reason=decision.reason,
                model=selected_model,
                request_count=usage.request_count,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            ),
        ]
    )
    _settle_lead_quota(db, user.id, reserved, usage.request_count)
    db.commit()
    _release_project_turn(db, project.id, turn_id)
    db.refresh(user_message)
    db.refresh(lead_message)
    return ProjectMessageResult(
        intent=decision.intent,
        user_message=_project_message_view(user_message),
        lead_message=_project_message_view(lead_message),
        proposal_id=(
            lead_message.id
            if decision.intent == ProjectLeadIntent.PROPOSE_CHANGE
            else None
        ),
        model=selected_model,
        fallback_provider=usage.fallback_provider,
    )


@router.post(
    "/projects/{project_id}/change-proposals/{proposal_id}/approve",
    response_model=RunView,
    status_code=status.HTTP_202_ACCEPTED,
)
def approve_project_change_proposal(
    project_id: str,
    proposal_id: str,
    background_tasks: BackgroundTasks,
    blueprint_executor: Callable[[str], None] = Depends(get_blueprint_executor),
    job_dispatcher: Callable[[str], None] = Depends(get_job_dispatcher),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RunView:
    project = _owned_project(db, project_id, user.id)
    proposal = db.get(ProjectMessage, proposal_id)
    if (
        proposal is None
        or proposal.project_id != project.id
        or proposal.user_id != user.id
        or proposal.role != "lead"
        or proposal.message_type != "change_proposal"
    ):
        raise AppError("CHANGE_PROPOSAL_NOT_FOUND", "Project change proposal was not found", 404)
    proposal_payload = dict(proposal.payload or {})
    if proposal_payload.get("status") == "approved" and proposal_payload.get("run_id"):
        existing_run = db.get(Run, str(proposal_payload["run_id"]))
        if existing_run is not None:
            return _run_view(db, existing_run)
    if proposal_payload.get("status") != "pending":
        raise AppError("CHANGE_PROPOSAL_NOT_PENDING", "Project change proposal is not pending", 409)

    request_message = db.get(ProjectMessage, proposal_payload.get("request_message_id"))
    if request_message is None or request_message.project_id != project.id:
        raise AppError("CHANGE_PROPOSAL_INVALID", "Proposal request message was not found", 409)
    selected_model = str(
        proposal_payload.get("model")
        or request_message.payload.get("model")
        or ""
    )
    model_config = models()
    if selected_model not in {option.id for option in model_config.models}:
        raise AppError("MODEL_NOT_ALLOWED", "Selected model is not available", 422)

    base_version_id = proposal_payload.get("base_version_id")
    if base_version_id != project.latest_version_id:
        proposal.payload = {**proposal_payload, "status": "stale"}
        db.commit()
        raise AppError(
            "BASE_VERSION_CHANGED",
            "The Project version changed after this proposal was prepared",
            409,
        )
    base_version = db.get(ProjectVersion, base_version_id) if base_version_id else None
    if base_version is not None and not base_version.git_commit:
        raise AppError("VERSION_NOT_FOUND", "The current Project version has no Git commit", 409)

    run = Run(
        project_id=project.id,
        session_id=proposal.session_id,
        user_id=user.id,
        mode=Mode.TEAM.value,
        model=selected_model,
        trigger="ai_edit" if base_version else "build",
        base_version_id=base_version.id if base_version else None,
        status=(
            RunStatus.BUILD_QUEUED.value
            if base_version
            else RunStatus.PRODUCT_RUNNING.value
        ),
        current_stage="team_leader" if base_version else "product_manager",
        prompt=request_message.content,
    )
    db.add(run)
    db.flush()
    claim_filters = [
        Project.id == project.id,
        Project.user_id == user.id,
        Project.active_write_run_id.is_(None),
    ]
    claim_filters.append(
        Project.latest_version_id == base_version.id
        if base_version
        else Project.latest_version_id.is_(None)
    )
    claimed = db.execute(
        update(Project)
        .where(*claim_filters)
        .values(
            active_write_run_id=run.id,
            status=ProjectStatus.BUILDING.value,
            **({"prompt": request_message.content} if base_version is None else {}),
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError("PROJECT_WRITE_BUSY", "Another operation is writing this Project", 409)

    request_message.run_id = run.id
    request_message.payload = {
        **request_message.payload,
        "base_version_id": base_version.id if base_version else None,
        "selected_files": proposal_payload.get("selected_files", []),
    }
    proposal.run_id = run.id
    proposal.payload = {**proposal_payload, "status": "approved", "run_id": run.id}
    if base_version:
        job = BuildJob(run_id=run.id, project_id=project.id, status=BuildStatus.QUEUED.value)
        db.add(job)
        db.flush()
        record_event(
            db,
            run.id,
            "project.change_queued",
            "Approved Project change queued from the current version",
            stage="team_leader",
            payload={
                "proposal_id": proposal.id,
                "base_version_id": base_version.id,
                "base_git_commit": base_version.git_commit,
                "build_job_id": job.id,
            },
        )
    else:
        previous_run = db.scalar(
            select(Run)
            .where(Run.project_id == project.id, Run.id != run.id)
            .order_by(Run.created_at.desc())
        )
        record_event(
            db,
            run.id,
            "project.recovery_started",
            "An approved recovery request is continuing in the existing Project",
            stage="product_manager",
            payload={
                "proposal_id": proposal.id,
                "retry_of_run_id": previous_run.id if previous_run else None,
            },
        )
    db.commit()
    if base_version:
        job_dispatcher(job.id)
    else:
        background_tasks.add_task(blueprint_executor, run.id)
    db.refresh(run)
    return _run_view(db, run)


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
    ArtifactType.CHANGE_BRIEF: ".another-atom/generated/change-brief.json",
    ArtifactType.REQUIREMENT_DELTA: ".another-atom/generated/requirement-delta.json",
    ArtifactType.BASE_SOURCE_SNAPSHOT: ".another-atom/generated/base-source-snapshot.json",
    ArtifactType.SOURCE_PATCH_SET: ".another-atom/generated/source-patch-set.json",
    ArtifactType.SOURCE_PATCH_APPLY_REPORT: (
        ".another-atom/generated/source-patch-apply-report.json"
    ),
    ArtifactType.SOURCE_DIFF: ".another-atom/generated/source-diff.json",
    ArtifactType.BLUEPRINT: ".another-atom/generated/blueprint.json",
    ArtifactType.ARCHITECTURE_DESIGN: ".another-atom/generated/architecture-design.json",
    ArtifactType.ARCHITECTURE_SPEC: ".another-atom/generated/architecture-spec.json",
    ArtifactType.APP_SPEC: ".another-atom/generated/app-spec.json",
    ArtifactType.APP_SPEC_REPAIR: ".another-atom/generated/app-spec-repair.json",
    ArtifactType.ENGINEER_OUTPUT_REPAIR: (
        ".another-atom/generated/engineer-output-repair.json"
    ),
    ArtifactType.SOURCE_BUNDLE: ".another-atom/generated/source-bundle.json",
    ArtifactType.BUILD_ARTIFACT: ".another-atom/generated/build-artifact.json",
    ArtifactType.EXECUTION_REPORT: ".another-atom/generated/execution-report.json",
    ArtifactType.DATA_PROFILE: ".another-atom/generated/data-profile.json",
    ArtifactType.VALIDATION_REPORT: ".another-atom/generated/validation-report.json",
    ArtifactType.REPAIR_VALIDATION_REPORT: (
        ".another-atom/generated/repair-validation-report.json"
    ),
    ArtifactType.REVIEW_REPORT: ".another-atom/generated/review-report.json",
    ArtifactType.PRODUCT_SPEC: ".another-atom/generated/product-spec.json",
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
        files = []
        for path, size in list_repository_files(project.id):
            kind, editable, render_mode = repository_file_capabilities(path)
            files.append(
                ProjectFileEntry(
                    path=path,
                    source="repository",
                    size=size,
                    kind=kind,
                    editable=editable,
                    render_mode=render_mode,
                )
            )
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
                        kind="json",
                        editable=False,
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
        kind, editable, render_mode = repository_file_capabilities(path)
        return ProjectFileContent(
            path=path,
            source="repository",
            content=content,
            content_hash=repository_content_hash(content),
            editable=editable,
            kind=kind,
            render_mode=render_mode,
        )

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
        content_hash=repository_content_hash(
            json.dumps(artifact.payload, ensure_ascii=False, indent=2) + "\n"
        ),
        editable=False,
        kind="json",
        render_mode="source",
    )


@router.put(
    "/projects/{project_id}/files/content",
    response_model=ProjectFileSaveResult,
)
def save_project_file_content(
    project_id: str,
    request: ProjectFileSaveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectFileSaveResult:
    project = _owned_project(db, project_id, user.id)
    existing = db.get(FileSaveOperation, request.operation_id)
    if existing is not None:
        if (
            existing.project_id != project.id
            or existing.user_id != user.id
            or existing.path != request.path
            or existing.expected_hash != request.expected_content_hash
        ):
            raise AppError(
                "FILE_SAVE_OPERATION_CONFLICT",
                "The operation id is already bound to another save",
                409,
            )
        if existing.status == "completed" and existing.git_commit and existing.target_hash:
            return ProjectFileSaveResult(
                path=existing.path,
                content_hash=existing.target_hash,
                size=len(request.content.encode("utf-8")),
                git_commit=existing.git_commit,
                saved_at=existing.updated_at,
            )
        if existing.status == "failed":
            raise AppError(
                existing.error_code or "REPOSITORY_FILE_SAVE_FAILED",
                "The previous save operation failed; retry with a new operation id",
                409,
            )
    else:
        existing = FileSaveOperation(
            id=request.operation_id,
            project_id=project.id,
            user_id=user.id,
            path=request.path,
            expected_hash=request.expected_content_hash,
            status="pending",
        )
        db.add(existing)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise AppError(
                "FILE_SAVE_OPERATION_CONFLICT",
                "The operation id is already in use",
                409,
            ) from exc

    kind, editable, _ = repository_file_capabilities(request.path)
    if not editable:
        existing.status = "failed"
        existing.error_code = "REPOSITORY_FILE_NOT_EDITABLE"
        db.commit()
        raise AppError(
            "REPOSITORY_FILE_NOT_EDITABLE",
            "Application source and Runtime files must use their validated edit flow",
            409,
        )
    if kind == "json":
        try:
            json.loads(request.content)
        except json.JSONDecodeError as exc:
            existing.status = "failed"
            existing.error_code = "REPOSITORY_FILE_VALIDATION_FAILED"
            db.commit()
            raise AppError(
                "REPOSITORY_FILE_VALIDATION_FAILED",
                f"JSON is invalid at line {exc.lineno}, column {exc.colno}",
                422,
            ) from exc

    claimed = db.execute(
        update(Project)
        .where(Project.id == project.id, Project.active_write_run_id.is_(None))
        .values(active_write_run_id=existing.id)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError(
            "PROJECT_WRITE_BUSY",
            "Another operation is currently writing this Project",
            409,
        )
    existing.status = "writing"
    db.commit()

    try:
        target_hash, git_commit, size = save_repository_text_file(
            project.id,
            request.path,
            request.content,
            request.expected_content_hash,
            existing.id,
        )
    except RepositoryError as exc:
        message = str(exc)
        if "changed after it was opened" in message:
            error_code, status_code = "REPOSITORY_FILE_CONFLICT", 409
        elif "read-only" in message:
            error_code, status_code = "REPOSITORY_FILE_NOT_EDITABLE", 409
        elif "too large" in message:
            error_code, status_code = "REPOSITORY_FILE_VALIDATION_FAILED", 422
        else:
            error_code, status_code = "REPOSITORY_FILE_SAVE_FAILED", 500
        operation = db.get(FileSaveOperation, request.operation_id)
        project = db.get(Project, project.id)
        assert operation is not None and project is not None
        operation.status = "failed"
        operation.error_code = error_code
        db.execute(
            update(Project)
            .where(Project.id == project.id, Project.active_write_run_id == operation.id)
            .values(active_write_run_id=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        raise AppError(error_code, message, status_code) from exc

    operation = db.get(FileSaveOperation, request.operation_id)
    project = db.get(Project, project.id)
    assert operation is not None and project is not None
    operation.status = "completed"
    operation.target_hash = target_hash
    operation.git_commit = git_commit
    db.execute(
        update(Project)
        .where(Project.id == project.id, Project.active_write_run_id == operation.id)
        .values(active_write_run_id=None)
        .execution_options(synchronize_session=False)
    )
    if target_hash != request.expected_content_hash:
        _record_project_event(
            db,
            project.id,
            "project.file.updated",
            "A Project document was updated",
            {
                "path": request.path,
                "old_hash": request.expected_content_hash,
                "new_hash": target_hash,
                "git_commit": git_commit,
                "operation_id": operation.id,
            },
        )
    db.commit()
    db.refresh(operation)
    return ProjectFileSaveResult(
        path=request.path,
        content_hash=target_hash,
        size=size,
        git_commit=git_commit,
        saved_at=operation.updated_at,
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
    operation_id = f"revision-{uuid4()}"
    claimed = db.execute(
        update(Project)
        .where(
            Project.id == project.id,
            Project.user_id == user.id,
            Project.latest_version_id == current.id,
            Project.active_write_run_id.is_(None),
        )
        .values(active_write_run_id=operation_id)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise AppError(
            "PROJECT_WRITE_BUSY",
            "Wait for the active Project change before creating another version",
            409,
        )
    db.commit()
    try:
        project = _owned_project(db, project_id, user.id)
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
        executed = _execute_version_candidate(
            db,
            current,
            app_spec,
            project.prompt,
            f"revision-{uuid4()}",
        )
        if executed is None:
            blueprint, architecture_spec = _validation_contracts(db, current.run_id)
            validation = validate_app_spec(
                app_spec,
                project.prompt,
                blueprint=blueprint,
                architecture_spec=architecture_spec,
            )
            execution_report = current.execution_report
            build_artifact = current.build_artifact
            source_bundle_payload = current.source_bundle
        else:
            execution_result, source_bundle = executed
            validation = execution_result.validation_report
            execution_report = execution_result.execution_report.model_dump(mode="json")
            build_artifact = (
                execution_result.build_artifact.model_dump(mode="json")
                if execution_result.build_artifact
                else None
            )
            source_bundle_payload = source_bundle.model_dump(mode="json")
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
            architecture_design=current.architecture_design,
            source_bundle=source_bundle_payload,
            execution_report=execution_report,
            build_artifact=build_artifact,
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
            SourceBundle.model_validate(source_bundle_payload)
            if source_bundle_payload
            else None,
        )
        project.latest_version_id = version.id
        db.execute(
            update(Project)
            .where(Project.id == project.id, Project.active_write_run_id == operation_id)
            .values(active_write_run_id=None)
            .execution_options(synchronize_session=False)
        )
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
    except Exception:
        db.rollback()
        db.execute(
            update(Project)
            .where(Project.id == project_id, Project.active_write_run_id == operation_id)
            .values(active_write_run_id=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        raise


@router.post("/projects/{project_id}/restore/{version_id}", response_model=VersionView)
def restore_version(
    project_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VersionView:
    project = _owned_project(db, project_id, user.id)
    if project.active_write_run_id:
        raise AppError(
            "PROJECT_WRITE_BUSY",
            "Wait for the active Project change before restoring a version",
            409,
        )
    source_version = db.scalar(
        select(ProjectVersion).where(
            ProjectVersion.id == version_id, ProjectVersion.project_id == project.id
        )
    )
    if source_version is None:
        raise AppError("VERSION_NOT_FOUND", "Restore version was not found", 404)
    restored_app_spec = AppSpec.model_validate(source_version.app_spec)
    executed = _execute_version_candidate(
        db,
        source_version,
        restored_app_spec,
        project.prompt,
        f"restore-{uuid4()}",
    )
    if executed is None:
        blueprint, architecture_spec = _validation_contracts(db, source_version.run_id)
        validation = validate_app_spec(
            restored_app_spec,
            project.prompt,
            blueprint=blueprint,
            architecture_spec=architecture_spec,
        )
        execution_report = source_version.execution_report
        build_artifact = source_version.build_artifact
        source_bundle_payload = source_version.source_bundle
    else:
        execution_result, source_bundle = executed
        validation = execution_result.validation_report
        execution_report = execution_result.execution_report.model_dump(mode="json")
        build_artifact = (
            execution_result.build_artifact.model_dump(mode="json")
            if execution_result.build_artifact
            else None
        )
        source_bundle_payload = source_bundle.model_dump(mode="json")
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
        architecture_design=source_version.architecture_design,
        source_bundle=source_bundle_payload,
        execution_report=execution_report,
        build_artifact=build_artifact,
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
        SourceBundle.model_validate(source_bundle_payload)
        if source_bundle_payload
        else None,
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


def _execute_version_candidate(
    db: Session,
    version: ProjectVersion,
    app_spec: AppSpec,
    prompt: str,
    execution_id: str,
) -> tuple[ExecutionResult, SourceBundle] | None:
    blueprint = _artifact_model(db, version.run_id, ArtifactType.BLUEPRINT, Blueprint)
    product_spec = _artifact_model(
        db, version.run_id, ArtifactType.PRODUCT_SPEC, ProductSpec
    )
    architecture_design = (
        ArchitectureDesign.model_validate(version.architecture_design)
        if version.architecture_design
        else _artifact_model(
            db,
            version.run_id,
            ArtifactType.ARCHITECTURE_DESIGN,
            ArchitectureDesign,
        )
    )
    if blueprint is None or product_spec is None or architecture_design is None:
        return None
    existing_bundle = (
        SourceBundle.model_validate(version.source_bundle)
        if version.source_bundle
        else _artifact_model(db, version.run_id, ArtifactType.SOURCE_BUNDLE, SourceBundle)
    )
    if existing_bundle is None:
        return None
    unit_tests = [
        SourceFileDraft.model_validate(
            item.model_dump(mode="python", exclude={"content_hash"})
        )
        for item in existing_bundle.files
        if item.role == "test"
    ]
    source_bundle = create_source_bundle(
        EngineerOutput(app_spec=app_spec, unit_tests=unit_tests),
        blueprint.product_type,
    )
    request_payload = {
        "execution_id": execution_id,
        "run_id": version.run_id,
        "attempt": 1,
        "adapter_id": source_bundle.adapter_id,
        "product_spec_hash": product_spec.content_hash,
        "architecture_design_hash": architecture_design.content_hash,
        "source_manifest_hash": source_bundle.manifest_hash,
        "prompt": prompt,
        "blueprint": blueprint.model_dump(mode="json"),
        "architecture_design": architecture_design.model_dump(mode="json"),
        "app_spec": app_spec.model_dump(mode="json"),
        "source_bundle": source_bundle.model_dump(mode="json"),
        "acceptance_criteria": architecture_design.acceptance_mapping,
        "deadline_ms": int(get_settings().runtime_executor_timeout_seconds * 1000),
    }
    request_hash = hashlib.sha256(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    try:
        _, result = execute_request(
            ExecutionRequest(**request_payload, request_hash=request_hash)
        )
    except RuntimeExecutorError as exc:
        raise AppError("RUNTIME_EXECUTOR_UNAVAILABLE", str(exc), 503) from exc
    return result, source_bundle


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
    claimed_project = db.execute(
        update(Project)
        .where(
            Project.id == project.id,
            Project.user_id == user.id,
            Project.active_write_run_id.is_(None),
        )
        .values(active_write_run_id=session.id)
        .execution_options(synchronize_session=False)
    )
    if claimed_project.rowcount != 1:
        db.rollback()
        current_project = _owned_project(db, project.id, user.id)
        if current_project.active_write_run_id == session.id:
            raise AppError(
                "SANDBOX_SAVE_NOT_ALLOWED",
                "Sandbox save is already in progress",
                409,
            )
        raise AppError(
            "PROJECT_WRITE_BUSY",
            "Wait for the active Project change before saving Vim changes",
            409,
        )
    db.commit()
    sandbox = sandbox_factory()
    try:
        _claim_sandbox_save(db, session)
    except Exception:
        db.execute(
            update(Project)
            .where(Project.id == project.id, Project.active_write_run_id == session.id)
            .values(active_write_run_id=None)
        )
        db.commit()
        raise
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
        executed = _execute_version_candidate(
            db,
            current,
            app_spec,
            project.prompt,
            f"sandbox-save-{uuid4()}",
        )
        if executed is None:
            blueprint, architecture_spec = _validation_contracts(db, current.run_id)
            validation = validate_app_spec(
                app_spec,
                project.prompt,
                blueprint=blueprint,
                architecture_spec=architecture_spec,
            )
            execution_report = current.execution_report
            build_artifact = current.build_artifact
            source_bundle_payload = current.source_bundle
        else:
            execution_result, source_bundle = executed
            validation = execution_result.validation_report
            execution_report = execution_result.execution_report.model_dump(mode="json")
            build_artifact = (
                execution_result.build_artifact.model_dump(mode="json")
                if execution_result.build_artifact
                else None
            )
            source_bundle_payload = source_bundle.model_dump(mode="json")
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
            architecture_design=current.architecture_design,
            source_bundle=source_bundle_payload,
            execution_report=execution_report,
            build_artifact=build_artifact,
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
            SourceBundle.model_validate(source_bundle_payload)
            if source_bundle_payload
            else None,
        )
        project.latest_version_id = version.id
        db.execute(
            update(Project)
            .where(Project.id == project.id, Project.active_write_run_id == session.id)
            .values(active_write_run_id=None)
            .execution_options(synchronize_session=False)
        )
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
        db.execute(
            update(Project)
            .where(Project.id == project.id, Project.active_write_run_id == session.id)
            .values(active_write_run_id=None)
        )
        db.commit()
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
