from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from another_atom.agent.provider import LLMProvider, LLMProviderError, get_llm_provider
from another_atom.build.renderer import validate_app_spec
from another_atom.contracts.schemas import (
    AppSpec,
    ArtifactType,
    Blueprint,
    BuildStatus,
    Mode,
    ProjectStatus,
    RunStatus,
    SupportLevel,
    VersionSource,
    VisualSpec,
)
from another_atom.domain.artifacts import get_artifact, save_artifact
from another_atom.domain.events import record_event
from another_atom.domain.quota import release_quota, settle_quota
from another_atom.storage.database import SessionLocal
from another_atom.storage.models import BuildJob, Deployment, Project, ProjectVersion, Run

T = TypeVar("T", bound=BaseModel)


class Orchestrator:
    def __init__(self, db: Session, provider: LLMProvider | None = None) -> None:
        self.db = db
        self.provider = provider or get_llm_provider()

    def create_blueprint(self, run: Run) -> Blueprint | None:
        run.current_stage = "product_manager"
        run.status = RunStatus.PRODUCT_RUNNING.value
        record_event(
            self.db,
            run.id,
            "stage.started",
            "Product Manager is structuring the request",
            stage="product_manager",
        )
        try:
            blueprint = self._with_retries(
                run,
                "product_manager",
                lambda: self.provider.create_blueprint(run.prompt, Mode(run.mode)),
            )
            artifact = save_artifact(self.db, run.id, ArtifactType.BLUEPRINT, blueprint)
            project = self.db.get(Project, run.project_id)
            if project:
                project.name = blueprint.project_name
            record_event(
                self.db,
                run.id,
                "artifact.created",
                "Blueprint is ready for review",
                stage="product_manager",
                payload={
                    "artifact_id": artifact.id,
                    "artifact_type": ArtifactType.BLUEPRINT.value,
                    "support_level": blueprint.support_level.value,
                },
            )
            if blueprint.support_level == SupportLevel.UNSUPPORTED:
                run.status = RunStatus.NEEDS_INPUT.value
                run.current_stage = "scope_review"
                record_event(
                    self.db,
                    run.id,
                    "run.needs_input",
                    "The request is outside the V1 catalog scope",
                    stage="scope_review",
                    payload={"rewrite_suggestion": blueprint.rewrite_suggestion},
                )
            else:
                run.status = RunStatus.AWAITING_APPROVAL.value
                run.current_stage = "blueprint_approval"
                record_event(
                    self.db,
                    run.id,
                    "approval.required",
                    "Review and confirm the Blueprint before building",
                    stage="blueprint_approval",
                )
            settle_quota(self.db, run, 1)
            self.db.commit()
            return blueprint
        except LLMProviderError as exc:
            self._fail_run(run, "LLM_OUTPUT_FAILED", str(exc), settle=True)
            return None

    def execute_approved_run(self, run_id: str) -> None:
        run = self.db.get(Run, run_id)
        if run is None:
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
                visual_spec = self._run_designer(run, blueprint)
            else:
                visual_spec = self.provider.create_visual_spec(blueprint)
                save_artifact(self.db, run.id, ArtifactType.VISUAL_SPEC, visual_spec)
            app_spec = self._run_engineer(run, blueprint, visual_spec)
            validation_report, build_job = self._run_build(run, project, app_spec)
            if not validation_report.passed:
                build_job.status = BuildStatus.FAILED.value
                build_job.error_message = "Deterministic validation failed"
                self._fail_run(
                    run,
                    "BUILD_VALIDATION_FAILED",
                    "The controlled renderer rejected the generated AppSpec",
                    settle=True,
                )
                return

            qa_review = self._run_qa(run, app_spec, validation_report)
            version = self._create_version(
                run,
                project,
                app_spec,
                validation_report.model_dump(mode="json"),
                qa_review.model_dump(mode="json"),
                VersionSource.BUILD,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = (
                RunStatus.COMPLETED_DEGRADED.value
                if qa_review.warnings
                else RunStatus.COMPLETED.value
            )
            run.current_stage = "complete"
            project.status = ProjectStatus.READY.value
            record_event(
                self.db,
                run.id,
                "run.completed",
                "Interactive preview is ready",
                stage="complete",
                payload={"version_id": version.id, "version_number": version.version_number},
            )
            settle_quota(self.db, run, run.quota_reserved)
            self.db.commit()
        except (LLMProviderError, ValueError) as exc:
            self._fail_run(run, "PIPELINE_FAILED", str(exc), settle=True)

    def _run_designer(self, run: Run, blueprint: Blueprint) -> VisualSpec:
        run.status = RunStatus.DESIGNER_RUNNING.value
        run.current_stage = "designer"
        record_event(
            self.db,
            run.id,
            "stage.started",
            "Designer is defining visual tokens",
            stage="designer",
        )
        visual_spec = self._with_retries(
            run, "designer", lambda: self.provider.create_visual_spec(blueprint)
        )
        artifact = save_artifact(self.db, run.id, ArtifactType.VISUAL_SPEC, visual_spec)
        record_event(
            self.db,
            run.id,
            "stage.completed",
            "VisualSpec passed schema validation",
            stage="designer",
            payload={"artifact_id": artifact.id},
        )
        self.db.commit()
        return visual_spec

    def _run_engineer(self, run: Run, blueprint: Blueprint, visual_spec: VisualSpec) -> AppSpec:
        run.status = RunStatus.ENGINEER_RUNNING.value
        run.current_stage = "engineer"
        record_event(
            self.db,
            run.id,
            "stage.started",
            "Engineer is producing the renderer contract",
            stage="engineer",
        )
        app_spec = self._with_retries(
            run,
            "engineer",
            lambda: self.provider.create_app_spec(blueprint, visual_spec, run.prompt),
        )
        artifact = save_artifact(self.db, run.id, ArtifactType.APP_SPEC, app_spec)
        record_event(
            self.db,
            run.id,
            "stage.completed",
            "AppSpec passed schema validation",
            stage="engineer",
            payload={"artifact_id": artifact.id},
        )
        self.db.commit()
        return app_spec

    def _run_build(self, run: Run, project: Project, app_spec: AppSpec):
        run.status = RunStatus.BUILDING.value
        run.current_stage = "build"
        build_job = self.db.scalar(select(BuildJob).where(BuildJob.run_id == run.id))
        if build_job is None:
            build_job = BuildJob(run_id=run.id, project_id=project.id)
            self.db.add(build_job)
            self.db.flush()
        build_job.status = BuildStatus.BUILDING.value
        build_job.attempt += 1
        record_event(
            self.db,
            run.id,
            "build.started",
            "Controlled React renderer started",
            stage="build",
            payload={"build_job_id": build_job.id},
        )
        validation_report = validate_app_spec(app_spec, run.prompt)
        save_artifact(self.db, run.id, ArtifactType.VALIDATION_REPORT, validation_report)
        build_job.status = BuildStatus.VALIDATING.value
        record_event(
            self.db,
            run.id,
            "validation.completed",
            "Deterministic route, data, and renderer checks completed",
            stage="build",
            payload={"passed": validation_report.passed},
        )
        self.db.commit()
        return validation_report, build_job

    def _run_qa(self, run: Run, app_spec: AppSpec, validation_report):
        run.status = RunStatus.QA_RUNNING.value
        run.current_stage = "qa"
        record_event(
            self.db,
            run.id,
            "stage.started",
            "QA is reviewing the deterministic validation result",
            stage="qa",
        )
        qa_review = self._with_retries(
            run,
            "qa",
            lambda: self.provider.review(app_spec, validation_report, run.prompt),
        )
        artifact = save_artifact(self.db, run.id, ArtifactType.QA_REVIEW, qa_review)
        record_event(
            self.db,
            run.id,
            "stage.completed",
            "QAReview is ready",
            stage="qa",
            payload={"artifact_id": artifact.id, "warnings": len(qa_review.warnings)},
        )
        self.db.commit()
        return qa_review

    def _create_version(
        self,
        run: Run,
        project: Project,
        app_spec: AppSpec,
        validation_report: dict,
        qa_review: dict,
        source: VersionSource,
    ) -> ProjectVersion:
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
            qa_review=qa_review,
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

    def _with_retries(
        self, run: Run, stage: str, operation: Callable[[], T], max_attempts: int = 3
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except (LLMProviderError, ValueError) as exc:
                last_error = exc
                record_event(
                    self.db,
                    run.id,
                    "agent.retry",
                    f"{stage} output failed validation; retrying",
                    stage=stage,
                    payload={"attempt": attempt, "max_attempts": max_attempts},
                )
                self.db.commit()
        raise LLMProviderError(str(last_error or "Agent output failed"))

    def _fail_run(self, run: Run, code: str, message: str, *, settle: bool = False) -> None:
        run.status = RunStatus.FAILED.value
        run.error_code = code
        run.error_message = message
        project = self.db.get(Project, run.project_id)
        if project and project.latest_version_id:
            project.status = ProjectStatus.READY.value
        elif project:
            project.status = ProjectStatus.DRAFT.value
        record_event(
            self.db,
            run.id,
            "run.failed",
            message,
            stage=run.current_stage,
            payload={"code": code},
        )
        if settle and run.quota_reserved:
            settle_quota(self.db, run, run.quota_reserved)
        else:
            release_quota(self.db, run)
        self.db.commit()


def execute_run_background(run_id: str) -> None:
    with SessionLocal() as db:
        Orchestrator(db).execute_approved_run(run_id)
