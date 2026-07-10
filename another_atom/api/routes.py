import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from another_atom.agent.orchestrator import Orchestrator
from another_atom.api.dependencies import get_current_user, get_job_dispatcher
from another_atom.build.renderer import validate_app_spec
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    ArtifactType,
    Blueprint,
    BlueprintApproval,
    BuildStatus,
    DataReview,
    DeploymentView,
    EventView,
    HealthView,
    Mode,
    ModelOption,
    ModelsView,
    ProjectStatus,
    ProjectView,
    PublicationStrategy,
    PublishRequest,
    QuotaView,
    RevisionRequest,
    RunCreate,
    RunStatus,
    RunView,
    SupportLevel,
    ValidationReport,
    VersionSource,
    VersionView,
)
from another_atom.domain.artifacts import get_artifact, save_artifact
from another_atom.domain.errors import AppError
from another_atom.domain.events import record_event
from another_atom.storage.database import SessionLocal, get_db
from another_atom.storage.models import (
    Approval,
    Attachment,
    BuildJob,
    Deployment,
    Project,
    ProjectSession,
    ProjectVersion,
    Run,
    RunEvent,
    User,
)

router = APIRouter(prefix="/api")


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
    return RunView(
        run_id=run.id,
        project_id=run.project_id,
        session_id=run.session_id,
        mode=Mode(run.mode),
        model=run.model,
        status=RunStatus(run.status),
        current_stage=run.current_stage,
        blueprint=_artifact_model(db, run.id, ArtifactType.BLUEPRINT, Blueprint),
        architecture_spec=_artifact_model(
            db, run.id, ArtifactType.ARCHITECTURE_SPEC, ArchitectureSpec
        ),
        app_spec=_artifact_model(db, run.id, ArtifactType.APP_SPEC, AppSpec),
        validation_report=_artifact_model(
            db, run.id, ArtifactType.VALIDATION_REPORT, ValidationReport
        ),
        data_review=_artifact_model(db, run.id, ArtifactType.DATA_REVIEW, DataReview),
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


@router.get("/quota", response_model=QuotaView)
def quota(user: User = Depends(get_current_user)) -> QuotaView:
    return QuotaView(
        limit=user.quota_limit,
        used=user.quota_used,
        reserved=user.quota_reserved,
        remaining=user.quota_limit - user.quota_used - user.quota_reserved,
    )


@router.get("/models", response_model=ModelsView)
def models() -> ModelsView:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return ModelsView(
            provider="ollama",
            default_model=settings.ollama_model,
            models=[
                ModelOption(id="deepseek-v4-pro", label="DeepSeek V4 Pro", usage="extra_high"),
                ModelOption(id="deepseek-v4-flash", label="DeepSeek V4 Flash", usage="medium"),
            ],
        )
    return ModelsView(
        provider="mock",
        default_model="mock",
        models=[ModelOption(id="mock", label="Mock LLM", usage="local")],
    )


@router.post("/runs", response_model=RunView, status_code=status.HTTP_201_CREATED)
def create_run(
    request: RunCreate,
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
    Orchestrator(db).create_blueprint(run)
    db.refresh(run)
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
    run = db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user.id).with_for_update())
    if run is None:
        raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
    if run.status != RunStatus.AWAITING_APPROVAL.value:
        raise AppError(
            "APPROVAL_NOT_ALLOWED", "This run is not waiting for Blueprint approval", 409
        )
    if approval.blueprint.support_level == SupportLevel.UNSUPPORTED:
        raise AppError(
            "UNSUPPORTED_REQUEST", "Unsupported requests cannot enter the build pipeline", 409
        )
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
    run.status = RunStatus.BUILD_QUEUED.value
    run.current_stage = "build_queue"
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
    app_spec = AppSpec.model_validate(app_spec.model_copy(update=updates))
    validation = validate_app_spec(app_spec, project.prompt)
    if not validation.passed:
        raise AppError("REVISION_VALIDATION_FAILED", "The revision failed validation", 422)
    data_review = DataReview.model_validate(current.data_review).model_copy(
        update={"engineering_checks": [check.label for check in validation.checks]}
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
        validation_report=validation.model_dump(mode="json"),
        data_review=data_review.model_dump(mode="json"),
    )
    db.add(version)
    db.flush()
    project.latest_version_id = version.id
    _advance_latest_deployment(db, project.id, version.id)
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
    validation = validate_app_spec(restored_app_spec, project.prompt)
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
        validation_report=validation.model_dump(mode="json"),
        data_review=source_version.data_review,
    )
    db.add(restored)
    db.flush()
    project.latest_version_id = restored.id
    _advance_latest_deployment(db, project.id, restored.id)
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


def _advance_latest_deployment(db: Session, project_id: str, version_id: str) -> None:
    deployment = db.scalar(
        select(Deployment).where(
            Deployment.project_id == project_id,
            Deployment.active.is_(True),
            Deployment.strategy == PublicationStrategy.ALWAYS_LATEST.value,
        )
    )
    if deployment:
        deployment.version_id = version_id


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
