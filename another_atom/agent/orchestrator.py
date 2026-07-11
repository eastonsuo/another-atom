from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from another_atom.agent.provider import LLMProvider, LLMProviderError, get_llm_provider
from another_atom.build.renderer import validate_app_spec
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    ArtifactType,
    Blueprint,
    BuildStatus,
    DataReview,
    Mode,
    ProjectStatus,
    RunStatus,
    SupportLevel,
    ValidationReport,
    VersionSource,
)
from another_atom.domain.artifacts import get_artifact, save_artifact
from another_atom.domain.errors import AppError
from another_atom.domain.events import record_event
from another_atom.domain.quota import release_quota, reserve_quota, settle_quota
from another_atom.storage.models import (
    Artifact,
    BuildJob,
    Deployment,
    Project,
    ProjectVersion,
    Run,
    RunEvent,
)

T = TypeVar("T", bound=BaseModel)


class Orchestrator:
    def __init__(self, db: Session, provider: LLMProvider | None = None) -> None:
        self.db = db
        self.provider_override = provider
        self.providers: dict[str, LLMProvider] = {}

    def _provider(self, run: Run) -> LLMProvider:
        if self.provider_override:
            return self.provider_override
        if run.model not in self.providers:
            self.providers[run.model] = get_llm_provider(model=run.model)
        return self.providers[run.model]

    def create_blueprint(self, run: Run) -> Blueprint | None:
        if run.status in {
            RunStatus.AWAITING_APPROVAL.value,
            RunStatus.NEEDS_INPUT.value,
            RunStatus.BUILD_QUEUED.value,
            RunStatus.ARCHITECT_RUNNING.value,
            RunStatus.ENGINEER_RUNNING.value,
            RunStatus.BUILDING.value,
            RunStatus.DATA_RUNNING.value,
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_DEGRADED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            artifact = get_artifact(self.db, run.id, ArtifactType.BLUEPRINT)
            return Blueprint.model_validate(artifact.payload) if artifact else None
        run.current_stage = "product_manager"
        run.status = RunStatus.PRODUCT_RUNNING.value
        self._record_event_once(
            run,
            "stage.started",
            "Product Manager is structuring the request",
            "product_manager",
        )
        try:
            blueprint, artifact, _ = self._run_agent_stage(
                run,
                "product_manager",
                ArtifactType.BLUEPRINT,
                Blueprint,
                lambda: self._provider(run).create_blueprint(run.prompt, Mode(run.mode)),
            )
            project = self.db.get(Project, run.project_id)
            if project:
                project.name = blueprint.project_name
            self._record_event_once(
                run,
                "artifact.created",
                "Blueprint is ready for review",
                "product_manager",
                {
                    "artifact_id": artifact.id,
                    "artifact_type": ArtifactType.BLUEPRINT.value,
                    "support_level": blueprint.support_level.value,
                },
            )
            if blueprint.support_level == SupportLevel.UNSUPPORTED:
                run.status = RunStatus.NEEDS_INPUT.value
                run.current_stage = "scope_review"
                self._record_event_once(
                    run,
                    "run.needs_input",
                    "The request is outside the V1 catalog scope",
                    "scope_review",
                    {"rewrite_suggestion": blueprint.rewrite_suggestion},
                )
            else:
                run.status = RunStatus.AWAITING_APPROVAL.value
                run.current_stage = "blueprint_approval"
                self._record_event_once(
                    run,
                    "approval.required",
                    "Review and confirm the Blueprint before building",
                    "blueprint_approval",
                )
            self.db.commit()
            return blueprint
        except LLMProviderError as exc:
            self._fail_run(run, "LLM_OUTPUT_FAILED", str(exc))
            return None
        except AppError as exc:
            self._fail_run(run, exc.code, exc.message)
            return None
        except Exception as exc:
            self.db.rollback()
            current = self.db.get(Run, run.id)
            if current:
                self._fail_run(current, "BLUEPRINT_FAILED", str(exc))
            return None

    def execute_approved_run(self, run_id: str) -> None:
        run = self.db.get(Run, run_id)
        if run is None:
            return
        if run.status not in {
            RunStatus.BUILD_QUEUED.value,
            RunStatus.ARCHITECT_RUNNING.value,
            RunStatus.ENGINEER_RUNNING.value,
            RunStatus.BUILDING.value,
            RunStatus.DATA_RUNNING.value,
        }:
            return
        project = self.db.get(Project, run.project_id)
        blueprint_artifact = get_artifact(self.db, run.id, ArtifactType.BLUEPRINT)
        if project is None or blueprint_artifact is None:
            self._fail_run(run, "MISSING_INPUT", "Approved Blueprint could not be loaded")
            return

        blueprint = Blueprint.model_validate(blueprint_artifact.payload)
        try:
            project.status = ProjectStatus.BUILDING.value
            if run.mode == Mode.TEAM.value:
                architecture_spec = self._run_architect(run, blueprint)
            else:
                architecture_spec, _, _ = self._run_agent_stage(
                    run,
                    "architect",
                    ArtifactType.ARCHITECTURE_SPEC,
                    ArchitectureSpec,
                    lambda: self._provider(run).create_architecture_spec(blueprint),
                )
            app_spec = self._run_engineer(run, blueprint, architecture_spec)
            validation_report, build_job = self._run_build(
                run, project, blueprint, architecture_spec, app_spec
            )
            if not validation_report.passed:
                build_job.status = BuildStatus.FAILED.value
                build_job.error_message = "Deterministic validation failed"
                self._fail_run(
                    run,
                    "BUILD_VALIDATION_FAILED",
                    "The controlled renderer rejected the generated AppSpec",
                )
                return

            data_review = self._run_data(run, app_spec, validation_report)
            version = self._create_version(
                run,
                project,
                app_spec,
                validation_report.model_dump(mode="json"),
                data_review.model_dump(mode="json"),
                VersionSource.BUILD,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = (
                RunStatus.COMPLETED_DEGRADED.value
                if data_review.warnings
                else RunStatus.COMPLETED.value
            )
            run.current_stage = "complete"
            project.status = ProjectStatus.READY.value
            self._record_event_once(
                run,
                "run.completed",
                "Interactive preview is ready",
                "complete",
                {"version_id": version.id, "version_number": version.version_number},
            )
            self.db.commit()
        except (LLMProviderError, ValueError) as exc:
            self._fail_run(run, "PIPELINE_FAILED", str(exc))
        except AppError as exc:
            self._fail_run(run, exc.code, exc.message)

    def _run_architect(self, run: Run, blueprint: Blueprint) -> ArchitectureSpec:
        run.status = RunStatus.ARCHITECT_RUNNING.value
        run.current_stage = "architect"
        self._record_event_once(
            run,
            "stage.started",
            "Architect is defining structure, data boundaries, and visual tokens",
            "architect",
        )
        architecture_spec, artifact, _ = self._run_agent_stage(
            run,
            "architect",
            ArtifactType.ARCHITECTURE_SPEC,
            ArchitectureSpec,
            lambda: self._provider(run).create_architecture_spec(blueprint),
        )
        self._record_event_once(
            run,
            "stage.completed",
            "ArchitectureSpec passed schema validation",
            "architect",
            {"artifact_id": artifact.id},
        )
        self.db.commit()
        return architecture_spec

    def _run_engineer(
        self, run: Run, blueprint: Blueprint, architecture_spec: ArchitectureSpec
    ) -> AppSpec:
        run.status = RunStatus.ENGINEER_RUNNING.value
        run.current_stage = "engineer"
        self._record_event_once(
            run,
            "stage.started",
            "Engineer is producing the renderer contract",
            "engineer",
        )
        app_spec, artifact, _ = self._run_agent_stage(
            run,
            "engineer",
            ArtifactType.APP_SPEC,
            AppSpec,
            lambda: self._provider(run).create_app_spec(blueprint, architecture_spec, run.prompt),
        )
        self._record_event_once(
            run,
            "stage.completed",
            "AppSpec passed schema validation",
            "engineer",
            {"artifact_id": artifact.id},
        )
        self.db.commit()
        return app_spec

    def _run_build(
        self,
        run: Run,
        project: Project,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
    ):
        run.status = RunStatus.BUILDING.value
        run.current_stage = "build"
        build_job = self.db.scalar(
            select(BuildJob)
            .where(BuildJob.run_id == run.id)
            .order_by(BuildJob.created_at.desc())
            .limit(1)
        )
        if build_job is None:
            build_job = BuildJob(run_id=run.id, project_id=project.id)
            self.db.add(build_job)
            self.db.flush()
        build_job.status = BuildStatus.BUILDING.value
        self._record_event_once(
            run,
            "build.started",
            "Controlled React renderer started",
            "build",
            {"build_job_id": build_job.id},
        )
        validation_artifact = get_artifact(self.db, run.id, ArtifactType.VALIDATION_REPORT)
        if validation_artifact:
            validation_report = ValidationReport.model_validate(validation_artifact.payload)
        else:
            validation_report = validate_app_spec(
                app_spec,
                run.prompt,
                blueprint=blueprint,
                architecture_spec=architecture_spec,
            )
            save_artifact(self.db, run.id, ArtifactType.VALIDATION_REPORT, validation_report)
        build_job.status = BuildStatus.VALIDATING.value
        self._record_event_once(
            run,
            "validation.completed",
            "Deterministic route, data, and renderer checks completed",
            "build",
            {"passed": validation_report.passed},
        )
        self.db.commit()
        return validation_report, build_job

    def _run_data(self, run: Run, app_spec: AppSpec, validation_report):
        run.status = RunStatus.DATA_RUNNING.value
        run.current_stage = "data"
        self._record_event_once(
            run,
            "stage.started",
            "Data Analyst is checking catalog data and validation evidence",
            "data",
        )
        data_review, artifact, _ = self._run_agent_stage(
            run,
            "data",
            ArtifactType.DATA_REVIEW,
            DataReview,
            lambda: self._provider(run).analyze(app_spec, validation_report, run.prompt),
        )
        self._record_event_once(
            run,
            "stage.completed",
            "DataReview is ready",
            "data",
            {"artifact_id": artifact.id, "warnings": len(data_review.warnings)},
        )
        self.db.commit()
        return data_review

    def _create_version(
        self,
        run: Run,
        project: Project,
        app_spec: AppSpec,
        validation_report: dict,
        data_review: dict,
        source: VersionSource,
    ) -> ProjectVersion:
        if source == VersionSource.BUILD:
            existing = self.db.scalar(
                select(ProjectVersion).where(
                    ProjectVersion.run_id == run.id,
                    ProjectVersion.source == VersionSource.BUILD.value,
                )
            )
            if existing:
                project.latest_version_id = existing.id
                return existing
        latest_number = self.db.scalar(
            select(func.max(ProjectVersion.version_number)).where(
                ProjectVersion.project_id == project.id
            )
        )
        version = ProjectVersion(
            project_id=project.id,
            run_id=run.id,
            version_number=(latest_number or 0) + 1,
            source=source.value,
            app_spec=app_spec.model_dump(mode="json"),
            validation_report=validation_report,
            data_review=data_review,
        )
        self.db.add(version)
        self.db.flush()
        project.latest_version_id = version.id
        deployment = self.db.scalar(
            select(Deployment).where(
                Deployment.project_id == project.id,
                Deployment.active.is_(True),
                Deployment.strategy == "always_latest",
            )
        )
        if deployment:
            deployment.version_id = version.id
        return version

    def _run_agent_stage(
        self,
        run: Run,
        stage: str,
        artifact_type: ArtifactType,
        model_type: type[T],
        operation: Callable[[], T],
        max_attempts: int = 3,
    ) -> tuple[T, Artifact, bool]:
        existing = get_artifact(self.db, run.id, artifact_type)
        if existing:
            return model_type.model_validate(existing.payload), existing, False
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            provider = self._provider(run)
            reserved_units = provider.reservation_units
            reserve_quota(self.db, run.user_id, run, stage, reserved_units)
            self.db.commit()
            try:
                result = operation()
                usage = provider.take_usage()
                artifact = save_artifact(self.db, run.id, artifact_type, result)
                settle_quota(
                    self.db,
                    run,
                    stage,
                    reserved_units,
                    usage,
                )
                self.db.commit()
                return result, artifact, True
            except (LLMProviderError, ValueError) as exc:
                last_error = exc
                usage = provider.take_usage()
                self.db.rollback()
                run = self.db.get(Run, run.id)
                if run is None:
                    raise
                if usage.request_count:
                    settle_quota(self.db, run, stage, reserved_units, usage)
                else:
                    release_quota(self.db, run, stage, reserved_units)
                record_event(
                    self.db,
                    run.id,
                    "agent.retry",
                    f"{stage} output failed validation; retrying",
                    stage=stage,
                    payload={"attempt": attempt, "max_attempts": max_attempts},
                )
                self.db.commit()
            except Exception:
                usage = provider.take_usage()
                self.db.rollback()
                current = self.db.get(Run, run.id)
                if current:
                    if usage.request_count:
                        settle_quota(self.db, current, stage, reserved_units, usage)
                    else:
                        release_quota(self.db, current, stage, reserved_units)
                    self.db.commit()
                raise
        if last_error is not None:
            raise last_error
        raise LLMProviderError("Agent output failed")

    def _fail_run(self, run: Run, code: str, message: str) -> None:
        run.status = RunStatus.FAILED.value
        run.error_code = code
        run.error_message = message
        project = self.db.get(Project, run.project_id)
        if project and project.latest_version_id:
            project.status = ProjectStatus.READY.value
        elif project:
            project.status = ProjectStatus.DRAFT.value
        self._record_event_once(
            run,
            "run.failed",
            message,
            run.current_stage,
            {"code": code},
        )
        release_quota(self.db, run, run.current_stage)
        self.db.commit()

    def _record_event_once(
        self,
        run: Run,
        event_type: str,
        message: str,
        stage: str,
        payload: dict | None = None,
    ) -> None:
        existing = self.db.scalar(
            select(RunEvent.id)
            .where(
                RunEvent.run_id == run.id,
                RunEvent.event_type == event_type,
                RunEvent.stage == stage,
            )
            .limit(1)
        )
        if existing is None:
            record_event(
                self.db,
                run.id,
                event_type,
                message,
                stage=stage,
                payload=payload,
            )
