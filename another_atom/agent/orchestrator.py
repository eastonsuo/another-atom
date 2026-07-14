import hashlib
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from another_atom.agent.provider import (
    LLMProvider,
    LLMProviderError,
    get_llm_provider,
    requires_pm_clarification,
)
from another_atom.build.renderer import normalize_architecture_visual_tokens, validate_app_spec
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    ArtifactType,
    BaseSourceSnapshot,
    Blueprint,
    BuildStatus,
    ChangeBrief,
    DataProfile,
    HumanTaskKind,
    HumanTaskStatus,
    LeadRoute,
    Mode,
    PMRequirementAssessment,
    PreviousFailureContext,
    ProductSpec,
    ProjectStatus,
    RequirementDelta,
    ReviewReport,
    RunStatus,
    SourceDiff,
    SupportLevel,
    ValidationReport,
    VersionSource,
)
from another_atom.domain.artifacts import get_artifact, save_artifact
from another_atom.domain.errors import AppError
from another_atom.domain.events import record_event
from another_atom.domain.quota import release_quota, reserve_quota, settle_quota
from another_atom.observability import get_logger
from another_atom.repository.service import (
    RepositoryError,
    build_source_snapshot,
    calculate_source_diff,
    commit_version,
    write_product_spec,
)
from another_atom.storage.models import (
    Artifact,
    BuildJob,
    HumanTask,
    Project,
    ProjectMessage,
    ProjectVersion,
    Run,
    RunEvent,
)

T = TypeVar("T", bound=BaseModel)
logger = get_logger("orchestrator")


def _contains_chinese(value: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in value)


def _render_product_spec(prompt: str, blueprint: Blueprint) -> ProductSpec:
    chinese = _contains_chinese(prompt)
    compact_goal = " ".join(prompt.split())
    if len(compact_goal) > 90:
        compact_goal = f"{compact_goal[:87]}..."
    if chinese:
        features = "、".join(blueprint.modules[:4])
        summary = f"{blueprint.project_name}面向“{compact_goal}”，主要包含{features}。"
        lines = [
            f"# {blueprint.project_name} 产品说明",
            "",
            "## 用户目标",
            "",
            prompt.strip(),
            "",
            "## 页面",
            "",
            *[f"- {item}" for item in blueprint.pages],
            "",
            "## 核心功能",
            "",
            *[f"- {item}" for item in blueprint.modules],
            "",
            "## 已映射需求",
            "",
            *([f"- {item}" for item in blueprint.mapped_requirements] or ["- 无"]),
            "",
            "## 当前能力边界",
            "",
            *([f"- {item}" for item in blueprint.omitted_requirements] or ["- 无额外删减"]),
            "",
            "## 数据与状态",
            "",
            *([f"- {item}" for item in blueprint.data_requirements] or ["- 无额外数据要求"]),
            "",
            "## 验收边界",
            "",
            "- 页面和核心功能可在当前 Web Runtime 中运行。",
            "- 被调整或省略的能力不会伪装成真实可用服务。",
        ]
    else:
        features = ", ".join(blueprint.modules[:4])
        summary = f'{blueprint.project_name} addresses "{compact_goal}" with {features}.'
        lines = [
            f"# {blueprint.project_name} Product Specification",
            "",
            "## User goal",
            "",
            prompt.strip(),
            "",
            "## Pages",
            "",
            *[f"- {item}" for item in blueprint.pages],
            "",
            "## Core features",
            "",
            *[f"- {item}" for item in blueprint.modules],
            "",
            "## Mapped requirements",
            "",
            *([f"- {item}" for item in blueprint.mapped_requirements] or ["- None"]),
            "",
            "## Capability boundary",
            "",
            *([f"- {item}" for item in blueprint.omitted_requirements] or ["- No omissions"]),
            "",
            "## Data and state",
            "",
            *(
                [f"- {item}" for item in blueprint.data_requirements]
                or ["- No extra data requirements"]
            ),
            "",
            "## Acceptance boundary",
            "",
            "- The pages and core features run in the current Web Runtime.",
            "- Adapted or omitted capabilities are not presented as real services.",
        ]
    content = "\n".join(lines).strip() + "\n"
    return ProductSpec(
        summary=summary,
        content=content,
        content_hash=f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}",
    )


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
            RunStatus.REVIEW_RUNNING.value,
            RunStatus.COMPLETED.value,
            RunStatus.COMPLETED_DEGRADED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            artifact = get_artifact(self.db, run.id, ArtifactType.BLUEPRINT)
            return Blueprint.model_validate(artifact.payload) if artifact else None
        run.current_stage = "product_manager"
        run.status = RunStatus.PRODUCT_RUNNING.value
        logger.info(
            "blueprint_stage_started",
            extra={
                "run_id": run.id,
                "project_id": run.project_id,
                "stage": "product_manager",
            },
        )
        self._record_event_once(
            run,
            "stage.started",
            "Product Manager is structuring the request",
            "product_manager",
        )
        try:
            effective_prompt = self._effective_prompt(run)
            assessment = (
                self._run_unpersisted_agent_stage(
                    run,
                    "product_manager_clarification",
                    lambda: self._provider(run).assess_requirements(effective_prompt),
                )
                if requires_pm_clarification(effective_prompt)
                else PMRequirementAssessment(
                    outcome="ready",
                    summary="The request is concrete enough to prepare a bounded product plan.",
                )
            )
            if assessment.outcome == "needs_input":
                self._pause_for_input(run, assessment, effective_prompt)
                return None
            self._record_event_once(
                run,
                "pm.requirements_ready",
                "Product Manager has enough information to prepare the Blueprint",
                "product_manager",
                {"summary": assessment.summary},
            )
            blueprint, artifact, _ = self._run_agent_stage(
                run,
                "product_manager",
                ArtifactType.BLUEPRINT,
                Blueprint,
                lambda: self._create_blueprint_in_request_language(
                    run, effective_prompt, Mode(run.mode)
                ),
            )
            regenerate_only = (
                self.db.scalar(
                    select(RunEvent.id).where(
                        RunEvent.run_id == run.id,
                        RunEvent.event_type == "alternative.regeneration_requested",
                    )
                )
                is not None
            )
            if regenerate_only:
                if blueprint.rewrite_suggestion:
                    draft = blueprint.rewrite_suggestion
                elif any("\u3400" <= character <= "\u9fff" for character in run.prompt):
                    draft = (
                        f"构建“{blueprint.project_name}”这一{blueprint.product_type}。"
                        f"页面：{'、'.join(blueprint.pages)}；功能：{'、'.join(blueprint.modules)}；"
                        f"视觉方向：{blueprint.visual_direction}。"
                    )
                else:
                    draft = (
                        f"Build {blueprint.project_name} as a {blueprint.product_type}. "
                        f"Screens: {', '.join(blueprint.pages)}. "
                        f"Features: {', '.join(blueprint.modules)}. "
                        f"Visual direction: {blueprint.visual_direction}."
                    )
                blueprint = blueprint.model_copy(
                    update={
                        "support_level": SupportLevel.UNSUPPORTED,
                        "support_reasons": [
                            "Product Manager regenerated this requirement for explicit user review."
                        ],
                        "rewrite_suggestion": draft,
                    }
                )
                artifact.payload = blueprint.model_dump(mode="json")
            product_spec = _render_product_spec(effective_prompt, blueprint)
            write_product_spec(run.project_id, product_spec.content)
            product_spec_artifact = save_artifact(
                self.db, run.id, ArtifactType.PRODUCT_SPEC, product_spec
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
                    "product_spec_artifact_id": product_spec_artifact.id,
                    "product_spec_path": product_spec.path,
                    "support_level": blueprint.support_level.value,
                },
            )
            if blueprint.support_level == SupportLevel.UNSUPPORTED:
                run.status = RunStatus.NEEDS_INPUT.value
                run.current_stage = "scope_review"
                self._record_event_once(
                    run,
                    "run.needs_input",
                    "The request needs user review before Web implementation",
                    "scope_review",
                    {"rewrite_suggestion": blueprint.rewrite_suggestion},
                )
            elif blueprint.support_level == SupportLevel.ADAPTED:
                run.status = RunStatus.AWAITING_APPROVAL.value
                run.current_stage = "blueprint_approval"
                self._create_human_task(
                    run,
                    kind=HumanTaskKind.APPROVAL,
                    stage="blueprint_approval",
                    prompt="查看并确认产品说明后继续构建",
                    subject=f"product_spec:{product_spec_artifact.id}:{product_spec.content_hash}",
                    payload={
                        "artifact_id": product_spec_artifact.id,
                        "artifact_type": ArtifactType.PRODUCT_SPEC.value,
                        "path": product_spec.path,
                        "content_hash": product_spec.content_hash,
                        "support_level": blueprint.support_level.value,
                    },
                )
                self._record_event_once(
                    run,
                    "approval.required",
                    "Review and confirm the product specification before building",
                    "blueprint_approval",
                )
            else:
                run.status = RunStatus.BUILD_QUEUED.value
                run.current_stage = "build_queue"
                build_job = self.db.scalar(select(BuildJob).where(BuildJob.run_id == run.id))
                if build_job is None:
                    build_job = BuildJob(
                        run_id=run.id,
                        project_id=run.project_id,
                        status=BuildStatus.QUEUED.value,
                    )
                    self.db.add(build_job)
                    self.db.flush()
                self._record_event_once(
                    run,
                    "build.auto_authorized",
                    "Supported Blueprint is within the requested scope and base budget",
                    "blueprint_approval",
                    {"authorization_source": "explicit_build_request"},
                )
                self._record_event_once(
                    run,
                    "build.queued",
                    "Build is queued",
                    "build_queue",
                    {"build_job_id": build_job.id},
                )
            self.db.commit()
            logger.info(
                "blueprint_stage_completed",
                extra={"run_id": run.id, "project_id": run.project_id, "status": run.status},
            )
            return blueprint
        except LLMProviderError as exc:
            logger.warning(
                "blueprint_stage_failed",
                extra={"run_id": run.id, "stage": "product_manager"},
            )
            self._fail_run(run, "LLM_OUTPUT_FAILED", str(exc))
            return None

        except AppError as exc:
            logger.warning(
                "blueprint_stage_failed",
                extra={"run_id": run.id, "stage": "product_manager"},
            )
            self._fail_run(run, exc.code, exc.message)
            return None
        except Exception as exc:
            logger.exception(
                "blueprint_stage_crashed",
                extra={"run_id": run.id, "stage": "product_manager"},
            )
            self.db.rollback()
            current = self.db.get(Run, run.id)
            if current:
                self._fail_run(current, "BLUEPRINT_FAILED", str(exc))
            return None

    def _create_blueprint_in_request_language(
        self, run: Run, prompt: str, mode: Mode
    ) -> Blueprint:
        blueprint = self._provider(run).create_blueprint(prompt, mode)
        if _contains_chinese(prompt):
            localized_fields = [
                *blueprint.support_reasons,
                *blueprint.mapped_requirements,
                *blueprint.omitted_requirements,
                *blueprint.pages,
                *blueprint.modules,
                blueprint.visual_direction,
                *blueprint.data_requirements,
                *([blueprint.rewrite_suggestion] if blueprint.rewrite_suggestion else []),
            ]
            if any(not _contains_chinese(value) for value in localized_fields):
                raise ValueError("Product Manager output must use the user's Chinese language")
        return blueprint

    def execute_approved_run(self, run_id: str) -> None:
        run = self.db.get(Run, run_id)
        if run is None:
            return
        if run.status not in {
            RunStatus.PRODUCT_RUNNING.value,
            RunStatus.BUILD_QUEUED.value,
            RunStatus.ARCHITECT_RUNNING.value,
            RunStatus.ENGINEER_RUNNING.value,
            RunStatus.BUILDING.value,
            RunStatus.DATA_RUNNING.value,
            RunStatus.REVIEW_RUNNING.value,
        }:
            return
        if run.trigger == "ai_edit":
            self._execute_change_run(run)
            return
        project = self.db.get(Project, run.project_id)
        blueprint_artifact = get_artifact(self.db, run.id, ArtifactType.BLUEPRINT)
        if project is None or blueprint_artifact is None:
            self._fail_run(run, "MISSING_INPUT", "Approved Blueprint could not be loaded")
            return

        blueprint = Blueprint.model_validate(blueprint_artifact.payload)
        try:
            logger.info(
                "build_pipeline_started",
                extra={"run_id": run.id, "project_id": run.project_id},
            )
            project.status = ProjectStatus.BUILDING.value
            if run.mode == Mode.TEAM.value:
                architecture_spec = self._run_architect(run, blueprint)
            else:
                architecture_spec, _, _ = self._run_agent_stage(
                    run,
                    "architect",
                    ArtifactType.ARCHITECTURE_SPEC,
                    ArchitectureSpec,
                    lambda: normalize_architecture_visual_tokens(
                        self._provider(run).create_architecture_spec(blueprint)
                    ),
                )
            app_spec = self._run_engineer(run, blueprint, architecture_spec)
            data_profile = self._run_data(run, blueprint, architecture_spec, app_spec)
            validation_report, build_job = self._run_build(
                run, project, blueprint, architecture_spec, app_spec
            )
            if not validation_report.passed and self._can_auto_repair(validation_report):
                app_spec = self._run_engineer_repair(
                    run,
                    blueprint,
                    architecture_spec,
                    app_spec,
                    validation_report,
                )
                validation_report = self._run_repair_validation(
                    run,
                    build_job,
                    blueprint,
                    architecture_spec,
                    app_spec,
                )
            if not validation_report.passed:
                build_job.status = BuildStatus.FAILED.value
                build_job.error_message = "Deterministic validation failed"
                self._fail_run(
                    run,
                    "BUILD_VALIDATION_FAILED",
                    "The Web source validator rejected the generated AppSpec",
                )
                return

            review_report = self._run_reviewer(
                run,
                blueprint,
                architecture_spec,
                app_spec,
                data_profile,
                validation_report,
            )
            if review_report.verdict != "accept" or any(
                issue.severity == "blocker" for issue in review_report.issues
            ):
                build_job.status = BuildStatus.FAILED.value
                build_job.error_message = "Reviewer requested rework or user input"
                self._fail_run(
                    run,
                    "REVIEW_REJECTED",
                    "The independent Reviewer found unresolved issues",
                )
                return
            version = self._create_version(
                run,
                project,
                app_spec,
                data_profile.model_dump(mode="json"),
                validation_report.model_dump(mode="json"),
                review_report.model_dump(mode="json"),
                VersionSource.BUILD,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = (
                RunStatus.COMPLETED_DEGRADED.value
                if data_profile.warnings or review_report.warnings
                else RunStatus.COMPLETED.value
            )
            run.current_stage = "complete"
            project.status = ProjectStatus.READY.value
            if project.active_write_run_id == run.id:
                project.active_write_run_id = None
            self._record_event_once(
                run,
                "run.completed",
                "Interactive preview is ready",
                "complete",
                {"version_id": version.id, "version_number": version.version_number},
            )
            self.db.commit()
            logger.info(
                "build_pipeline_completed",
                extra={
                    "run_id": run.id,
                    "project_id": run.project_id,
                    "status": run.status,
                },
            )
        except (LLMProviderError, ValueError) as exc:
            logger.warning(
                "build_pipeline_failed",
                extra={"run_id": run.id, "stage": run.current_stage},
            )
            self._fail_run(run, "PIPELINE_FAILED", str(exc))
        except AppError as exc:
            logger.warning(
                "build_pipeline_failed",
                extra={"run_id": run.id, "stage": run.current_stage},
            )
            self._fail_run(run, exc.code, exc.message)

    def _execute_change_run(self, run: Run) -> None:
        project = self.db.get(Project, run.project_id)
        base_version = self.db.get(ProjectVersion, run.base_version_id)
        if (
            project is None
            or base_version is None
            or base_version.project_id != run.project_id
            or not base_version.git_commit
        ):
            self._fail_run(run, "BASE_VERSION_NOT_FOUND", "The Project base version is unavailable")
            return
        effective_prompt = self._effective_prompt(run)
        try:
            lead_decision = self._run_unpersisted_agent_stage(
                run,
                "team_leader",
                lambda: self._provider(run).route_message(effective_prompt),
            )
            if lead_decision.route == LeadRoute.DIRECT:
                run.status = RunStatus.COMPLETED.value
                run.current_stage = "complete"
                project.status = ProjectStatus.READY.value
                if project.active_write_run_id == run.id:
                    project.active_write_run_id = None
                self._record_project_message_once(
                    run,
                    "lead",
                    "answer",
                    lead_decision.response,
                    {"reason": lead_decision.reason},
                )
                self._record_event_once(
                    run,
                    "lead.answered",
                    "Lead answered without starting a code change",
                    "team_leader",
                    {"reason": lead_decision.reason},
                )
                self.db.commit()
                return
        except (LLMProviderError, ValueError) as exc:
            self._fail_run(run, "CHANGE_PIPELINE_FAILED", str(exc))
            return
        try:
            assessment = (
                self._run_unpersisted_agent_stage(
                    run,
                    "product_manager_clarification",
                    lambda: self._provider(run).assess_requirements(
                        effective_prompt,
                        {
                            "project_id": project.id,
                            "base_version_id": base_version.id,
                            "request_type": "project_change",
                        },
                    ),
                )
                if requires_pm_clarification(effective_prompt)
                else PMRequirementAssessment(
                    outcome="ready",
                    summary="The requested Project change is concrete enough to proceed.",
                )
            )
        except (LLMProviderError, ValueError) as exc:
            self._fail_run(run, "PM_CLARIFICATION_FAILED", str(exc))
            return
        if assessment.outcome == "needs_input":
            self._pause_for_input(run, assessment, effective_prompt)
            return
        if project.active_write_run_id != run.id:
            self._fail_run(
                run,
                "PROJECT_WRITE_CONFLICT",
                "The Project write lease is no longer owned",
            )
            return

        blueprint_artifact = get_artifact(self.db, run.id, ArtifactType.BLUEPRINT)
        if blueprint_artifact is None:
            source_blueprint = get_artifact(self.db, base_version.run_id, ArtifactType.BLUEPRINT)
            if source_blueprint is None:
                self._fail_run(run, "MISSING_INPUT", "The current Blueprint could not be loaded")
                return
            blueprint_artifact = save_artifact(
                self.db,
                run.id,
                ArtifactType.BLUEPRINT,
                Blueprint.model_validate(source_blueprint.payload),
            )
            self.db.commit()
        blueprint = Blueprint.model_validate(blueprint_artifact.payload)
        base_app_spec = AppSpec.model_validate(base_version.app_spec)
        source_architecture = get_artifact(
            self.db, base_version.run_id, ArtifactType.ARCHITECTURE_SPEC
        )
        if source_architecture is None:
            self._fail_run(run, "MISSING_INPUT", "The current ArchitectureSpec could not be loaded")
            return
        base_architecture = ArchitectureSpec.model_validate(source_architecture.payload)

        try:
            project.status = ProjectStatus.BUILDING.value
            snapshot_artifact = get_artifact(
                self.db, run.id, ArtifactType.BASE_SOURCE_SNAPSHOT
            )
            if snapshot_artifact:
                source_snapshot = BaseSourceSnapshot.model_validate(snapshot_artifact.payload)
            else:
                source_snapshot = build_source_snapshot(
                    project.id, base_version.id, base_version.git_commit
                )
                save_artifact(
                    self.db, run.id, ArtifactType.BASE_SOURCE_SNAPSHOT, source_snapshot
                )
                self.db.commit()

            run.status = RunStatus.PRODUCT_RUNNING.value
            run.current_stage = "team_leader"
            previous_failure = self._previous_failure_context(run)
            self._record_event_once(
                run,
                "stage.started",
                "Lead is framing the requested Project change",
                "team_leader",
                {
                    "base_version_id": base_version.id,
                    "previous_failed_run_id": (
                        previous_failure.run_id if previous_failure else None
                    ),
                },
            )
            change_brief, change_artifact, _ = self._run_agent_stage(
                run,
                "team_leader",
                ArtifactType.CHANGE_BRIEF,
                ChangeBrief,
                lambda: self._provider(run).create_change_brief(
                    effective_prompt, blueprint, base_app_spec, previous_failure
                ),
            )
            if previous_failure and change_brief.previous_failure != previous_failure:
                change_brief = change_brief.model_copy(
                    update={"previous_failure": previous_failure}
                )
                change_artifact.payload = change_brief.model_dump(mode="json")
            self._record_event_once(
                run,
                "stage.completed",
                "Lead produced a bounded change brief",
                "team_leader",
                {"artifact_id": change_artifact.id},
            )
            self._record_project_message_once(
                run,
                "lead",
                "change_brief",
                change_brief.goal,
                change_brief.model_dump(mode="json"),
            )
            self.db.commit()

            run.current_stage = "product_manager"
            self._record_event_once(
                run,
                "stage.started",
                "Product Manager is defining the smallest requirement delta",
                "product_manager",
            )
            requirement_delta, requirement_artifact, _ = self._run_agent_stage(
                run,
                "product_manager",
                ArtifactType.REQUIREMENT_DELTA,
                RequirementDelta,
                lambda: self._provider(run).create_requirement_delta(change_brief, blueprint),
            )
            self._record_event_once(
                run,
                "stage.completed",
                "Requirement delta is ready",
                "product_manager",
                {"artifact_id": requirement_artifact.id},
            )
            self.db.commit()

            run.status = RunStatus.ARCHITECT_RUNNING.value
            run.current_stage = "architect"
            self._record_event_once(
                run,
                "stage.started",
                "Architect is checking the change against the current design",
                "architect",
            )
            architecture_spec, architecture_artifact, _ = self._run_agent_stage(
                run,
                "architect",
                ArtifactType.ARCHITECTURE_SPEC,
                ArchitectureSpec,
                lambda: normalize_architecture_visual_tokens(
                    self._provider(run).revise_architecture_spec(
                        blueprint,
                        base_architecture,
                        change_brief,
                        requirement_delta,
                    )
                ),
            )
            self._record_event_once(
                run,
                "stage.completed",
                "Revised ArchitectureSpec passed schema validation",
                "architect",
                {"artifact_id": architecture_artifact.id},
            )
            self.db.commit()

            run.status = RunStatus.ENGINEER_RUNNING.value
            run.current_stage = "engineer"
            self._record_event_once(
                run,
                "stage.started",
                "Engineer is modifying the current Project source",
                "engineer",
            )
            app_spec, app_artifact, _ = self._run_agent_stage(
                run,
                "engineer",
                ArtifactType.APP_SPEC,
                AppSpec,
                lambda: self._align_app_spec_visual_tokens(
                    self._provider(run).revise_app_spec(
                        blueprint,
                        architecture_spec,
                        base_app_spec,
                        change_brief,
                        requirement_delta,
                    ),
                    architecture_spec,
                ),
            )
            self._record_event_once(
                run,
                "stage.completed",
                "Candidate AppSpec passed schema validation",
                "engineer",
                {"artifact_id": app_artifact.id},
            )
            diff_artifact = get_artifact(self.db, run.id, ArtifactType.SOURCE_DIFF)
            if diff_artifact is None:
                source_diff = calculate_source_diff(source_snapshot, app_spec)
                diff_artifact = save_artifact(
                    self.db, run.id, ArtifactType.SOURCE_DIFF, source_diff
                )
            else:
                source_diff = SourceDiff.model_validate(diff_artifact.payload)
            if not (
                source_diff.changed_files
                or source_diff.added_files
                or source_diff.removed_files
            ):
                raise AppError(
                    "EMPTY_CHANGE",
                    "The requested change produced no source changes",
                    422,
                )
            self._record_event_once(
                run,
                "source.diff_created",
                "Runtime calculated the candidate source diff",
                "engineer",
                {
                    "changed_files": source_diff.changed_files,
                    "added_files": source_diff.added_files,
                    "removed_files": source_diff.removed_files,
                },
            )
            self.db.commit()

            data_profile = self._run_data(run, blueprint, architecture_spec, app_spec)
            validation_report, build_job = self._run_build(
                run, project, blueprint, architecture_spec, app_spec
            )
            if not validation_report.passed and self._can_auto_repair(validation_report):
                app_spec = self._run_engineer_repair(
                    run, blueprint, architecture_spec, app_spec, validation_report
                )
                validation_report = self._run_repair_validation(
                    run, build_job, blueprint, architecture_spec, app_spec
                )
                source_diff = calculate_source_diff(source_snapshot, app_spec)
                save_artifact(self.db, run.id, ArtifactType.SOURCE_DIFF, source_diff)
                self.db.commit()
            if not validation_report.passed:
                build_job.status = BuildStatus.FAILED.value
                self._fail_run(
                    run,
                    "BUILD_VALIDATION_FAILED",
                    "The Web source validator rejected the modified AppSpec",
                )
                return
            review_report = self._run_reviewer(
                run,
                blueprint,
                architecture_spec,
                app_spec,
                data_profile,
                validation_report,
            )
            if review_report.verdict != "accept" or any(
                issue.severity == "blocker" for issue in review_report.issues
            ):
                build_job.status = BuildStatus.FAILED.value
                self._fail_run(
                    run,
                    "REVIEW_REJECTED",
                    "The independent Reviewer found unresolved issues",
                )
                return
            self.db.refresh(project)
            if (
                project.active_write_run_id != run.id
                or project.latest_version_id != run.base_version_id
            ):
                raise AppError(
                    "BASE_VERSION_CHANGED",
                    "The Project changed while this modification was running",
                    409,
                )
            version = self._create_version(
                run,
                project,
                app_spec,
                data_profile.model_dump(mode="json"),
                validation_report.model_dump(mode="json"),
                review_report.model_dump(mode="json"),
                VersionSource.AI_EDIT,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = (
                RunStatus.COMPLETED_DEGRADED.value
                if data_profile.warnings or review_report.warnings
                else RunStatus.COMPLETED.value
            )
            run.current_stage = "complete"
            project.status = ProjectStatus.READY.value
            project.active_write_run_id = None
            self._record_event_once(
                run,
                "run.completed",
                "The Project change is ready as a new version",
                "complete",
                {"version_id": version.id, "version_number": version.version_number},
            )
            self._record_project_message_once(
                run,
                "system",
                "result",
                f"修改已完成并生成版本 v{version.version_number}。",
                {"version_id": version.id, "version_number": version.version_number},
            )
            self.db.commit()
        except (LLMProviderError, ValueError, RepositoryError) as exc:
            self._fail_run(run, "CHANGE_PIPELINE_FAILED", str(exc))
        except AppError as exc:
            self._fail_run(run, exc.code, exc.message)
        except Exception as exc:
            logger.exception(
                "change_pipeline_crashed",
                extra={"run_id": run.id, "stage": run.current_stage},
            )
            self.db.rollback()
            current = self.db.get(Run, run.id)
            if current:
                self._fail_run(current, "CHANGE_PIPELINE_FAILED", str(exc))

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
            lambda: normalize_architecture_visual_tokens(
                self._provider(run).create_architecture_spec(blueprint)
            ),
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
            "Engineer is generating the Web source contract",
            "engineer",
        )
        app_spec, artifact, _ = self._run_agent_stage(
            run,
            "engineer",
            ArtifactType.APP_SPEC,
            AppSpec,
            lambda: self._align_app_spec_visual_tokens(
                self._provider(run).create_app_spec(blueprint, architecture_spec, run.prompt),
                architecture_spec,
            ),
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

    def _run_engineer_repair(
        self,
        run: Run,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        validation_report: ValidationReport,
    ) -> AppSpec:
        run.status = RunStatus.ENGINEER_RUNNING.value
        run.current_stage = "engineer"
        failed_check_ids = [
            check.check_id for check in validation_report.checks if check.status == "fail"
        ]
        self._record_event_once(
            run,
            "repair.started",
            "Engineer is repairing the failed validation checks",
            "engineer",
            {"failed_check_ids": failed_check_ids, "repair_attempt": 1},
        )
        repaired_app_spec, artifact, _ = self._run_agent_stage(
            run,
            "engineer_repair",
            ArtifactType.APP_SPEC_REPAIR,
            AppSpec,
            lambda: self._align_app_spec_visual_tokens(
                self._provider(run).repair_app_spec(
                    blueprint,
                    architecture_spec,
                    app_spec,
                    validation_report,
                    run.prompt,
                ),
                architecture_spec,
            ),
        )
        self._record_event_once(
            run,
            "repair.completed",
            "Engineer produced one revised AppSpec",
            "engineer",
            {"artifact_id": artifact.id, "repair_attempt": 1},
        )
        self.db.commit()
        return repaired_app_spec

    @staticmethod
    def _align_app_spec_visual_tokens(
        app_spec: AppSpec, architecture_spec: ArchitectureSpec
    ) -> AppSpec:
        return app_spec.model_copy(
            update={
                "primary_color": architecture_spec.primary_color,
                "accent_color": architecture_spec.accent_color,
                "background_color": architecture_spec.background_color,
            }
        )

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
            "Web source packaging and sandbox validation started",
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
            "Deterministic source, capability, handoff, and visual checks completed",
            "build",
            {"passed": validation_report.passed},
        )
        self.db.commit()
        return validation_report, build_job

    def _run_repair_validation(
        self,
        run: Run,
        build_job: BuildJob,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
    ) -> ValidationReport:
        run.status = RunStatus.BUILDING.value
        run.current_stage = "build"
        build_job.status = BuildStatus.VALIDATING.value
        artifact = get_artifact(self.db, run.id, ArtifactType.REPAIR_VALIDATION_REPORT)
        if artifact:
            validation_report = ValidationReport.model_validate(artifact.payload)
        else:
            validation_report = validate_app_spec(
                app_spec,
                run.prompt,
                blueprint=blueprint,
                architecture_spec=architecture_spec,
            )
            artifact = save_artifact(
                self.db,
                run.id,
                ArtifactType.REPAIR_VALIDATION_REPORT,
                validation_report,
            )
        self._record_event_once(
            run,
            "repair.validation_completed",
            "The revised AppSpec completed deterministic validation",
            "build",
            {
                "artifact_id": artifact.id,
                "passed": validation_report.passed,
                "repair_attempt": 1,
            },
        )
        self.db.commit()
        return validation_report

    @staticmethod
    def _can_auto_repair(validation_report: ValidationReport) -> bool:
        failed_checks = [check for check in validation_report.checks if check.status == "fail"]
        return bool(failed_checks) and all(
            check.root_cause == "app_spec" and check.resolvable for check in failed_checks
        )

    def _run_data(
        self,
        run: Run,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
    ) -> DataProfile:
        run.status = RunStatus.DATA_RUNNING.value
        run.current_stage = "data"
        self._record_event_once(
            run,
            "stage.started",
            "Data Analyst is analyzing application data and local state",
            "data",
        )
        data_profile, artifact, _ = self._run_agent_stage(
            run,
            "data",
            ArtifactType.DATA_PROFILE,
            DataProfile,
            lambda: self._provider(run).analyze_data(
                blueprint,
                architecture_spec,
                app_spec,
                run.prompt,
            ),
        )
        self._record_event_once(
            run,
            "stage.completed",
            "DataProfile is ready",
            "data",
            {"artifact_id": artifact.id, "warnings": len(data_profile.warnings)},
        )
        self.db.commit()
        return data_profile

    def _run_reviewer(
        self,
        run: Run,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        data_profile: DataProfile,
        validation_report: ValidationReport,
    ) -> ReviewReport:
        run.status = RunStatus.REVIEW_RUNNING.value
        run.current_stage = "reviewer"
        self._record_event_once(
            run,
            "stage.started",
            "Reviewer is checking requirement coverage and immutable evidence",
            "reviewer",
        )
        review_report, artifact, _ = self._run_agent_stage(
            run,
            "reviewer",
            ArtifactType.REVIEW_REPORT,
            ReviewReport,
            lambda: self._provider(run).review(
                blueprint,
                architecture_spec,
                app_spec,
                data_profile,
                validation_report,
                run.prompt,
            ),
        )
        self._record_event_once(
            run,
            "stage.completed",
            "ReviewReport is ready",
            "reviewer",
            {
                "artifact_id": artifact.id,
                "verdict": review_report.verdict,
                "warnings": len(review_report.warnings),
            },
        )
        self.db.commit()
        return review_report

    def _create_version(
        self,
        run: Run,
        project: Project,
        app_spec: AppSpec,
        data_profile: dict,
        validation_report: dict,
        review_report: dict,
        source: VersionSource,
    ) -> ProjectVersion:
        if source in {VersionSource.BUILD, VersionSource.AI_EDIT}:
            existing = self.db.scalar(
                select(ProjectVersion).where(
                    ProjectVersion.run_id == run.id,
                    ProjectVersion.source == source.value,
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
            data_profile=data_profile,
            validation_report=validation_report,
            review_report=review_report,
        )
        self.db.add(version)
        self.db.flush()
        version.git_commit = commit_version(
            project.id,
            version.id,
            version.version_number,
            source,
            app_spec,
        )
        project.latest_version_id = version.id
        return version

    def _previous_failure_context(self, run: Run) -> PreviousFailureContext | None:
        previous = self.db.scalar(
            select(Run)
            .where(
                Run.project_id == run.project_id,
                Run.trigger == "ai_edit",
                Run.id != run.id,
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
        if previous is None or previous.status != RunStatus.FAILED.value:
            return None
        artifact_types = list(
            self.db.scalars(
                select(Artifact.artifact_type)
                .where(Artifact.run_id == previous.id)
                .order_by(Artifact.created_at.asc())
            ).all()
        )
        return PreviousFailureContext(
            run_id=previous.id,
            stage=previous.current_stage,
            error_code=previous.error_code,
            error_message=previous.error_message,
            artifact_types=artifact_types[:20],
        )

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
                if usage.fallback_provider:
                    logger.warning(
                        "provider_fallback_used",
                        extra={
                            "run_id": run.id,
                            "stage": stage,
                            "provider": usage.fallback_provider,
                        },
                    )
                    record_event(
                        self.db,
                        run.id,
                        "provider.fallback",
                        "Ollama timed out; switched to DeepSeek official API",
                        stage=stage,
                        payload={"provider": usage.fallback_provider},
                    )
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
                logger.warning(
                    "agent_stage_attempt_failed",
                    extra={"run_id": run.id, "stage": stage, "status": f"attempt_{attempt}"},
                )
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
                logger.exception("agent_stage_crashed", extra={"run_id": run.id, "stage": stage})
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

    def _run_unpersisted_agent_stage(
        self,
        run: Run,
        stage: str,
        operation: Callable[[], T],
        max_attempts: int = 3,
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            provider = self._provider(run)
            reserved_units = provider.reservation_units
            reserve_quota(self.db, run.user_id, run, stage, reserved_units)
            self.db.commit()
            try:
                result = operation()
                usage = provider.take_usage()
                if usage.fallback_provider:
                    record_event(
                        self.db,
                        run.id,
                        "provider.fallback",
                        "Ollama timed out; switched to DeepSeek official API",
                        stage=stage,
                        payload={"provider": usage.fallback_provider},
                    )
                settle_quota(self.db, run, stage, reserved_units, usage)
                self.db.commit()
                return result
            except (LLMProviderError, ValueError) as exc:
                last_error = exc
                usage = provider.take_usage()
                self.db.rollback()
                current = self.db.get(Run, run.id)
                if current is None:
                    raise
                run = current
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

    def _effective_prompt(self, run: Run) -> str:
        answers = self.db.scalars(
            select(HumanTask)
            .where(
                HumanTask.run_id == run.id,
                HumanTask.kind == HumanTaskKind.INPUT_REQUEST.value,
                HumanTask.status == HumanTaskStatus.ANSWERED.value,
            )
            .order_by(HumanTask.created_at, HumanTask.id)
        ).all()
        response_text = [
            str((task.response or {}).get("text", "")).strip()
            for task in answers
            if str((task.response or {}).get("text", "")).strip()
        ]
        if not response_text:
            return run.prompt
        label = (
            "用户补充"
            if any("\u3400" <= char <= "\u9fff" for char in run.prompt)
            else "User clarification"
        )
        return f"{run.prompt}\n\n{label}:\n" + "\n".join(response_text)

    def _create_human_task(
        self,
        run: Run,
        *,
        kind: HumanTaskKind,
        stage: str,
        prompt: str,
        subject: str,
        payload: dict | None = None,
    ) -> HumanTask:
        attempt = 0
        while True:
            unique_subject = subject if attempt == 0 else f"{subject}:repeat:{attempt}"
            subject_hash = hashlib.sha256(unique_subject.encode("utf-8")).hexdigest()
            existing = self.db.scalar(
                select(HumanTask).where(
                    HumanTask.run_id == run.id,
                    HumanTask.kind == kind.value,
                    HumanTask.subject_hash == subject_hash,
                )
            )
            if existing is None:
                break
            if existing.status == HumanTaskStatus.PENDING.value:
                return existing
            attempt += 1
        task = HumanTask(
            project_id=run.project_id,
            run_id=run.id,
            user_id=run.user_id,
            kind=kind.value,
            status=HumanTaskStatus.PENDING.value,
            stage=stage,
            prompt=prompt,
            subject_hash=subject_hash,
            payload=payload or {},
        )
        self.db.add(task)
        self.db.flush()
        return task

    def _pause_for_input(
        self,
        run: Run,
        assessment: PMRequirementAssessment,
        effective_prompt: str,
    ) -> None:
        question = assessment.question or "Please clarify the result you want to build."
        task = self._create_human_task(
            run,
            kind=HumanTaskKind.INPUT_REQUEST,
            stage="product_manager",
            prompt=question,
            subject=f"pm:{effective_prompt}:{question}",
            payload={
                "summary": assessment.summary,
                "missing_fields": assessment.missing_fields,
                "resume_stage": "product_manager",
                "base_version_id": run.base_version_id,
            },
        )
        run.status = RunStatus.NEEDS_INPUT.value
        run.current_stage = "product_manager_clarification"
        project = self.db.get(Project, run.project_id)
        if project is not None:
            project.status = (
                ProjectStatus.READY.value
                if project.latest_version_id
                else ProjectStatus.DRAFT.value
            )
            if project.active_write_run_id == run.id:
                project.active_write_run_id = None
        self.db.add(
            ProjectMessage(
                project_id=run.project_id,
                session_id=run.session_id,
                user_id=run.user_id,
                run_id=run.id,
                role="lead",
                message_type="clarification",
                content=question,
                payload={"human_task_id": task.id, **task.payload},
            )
        )
        self._record_event_once(
            run,
            "human_task.input_requested",
            question,
            "product_manager_clarification",
            {"human_task_id": task.id, "missing_fields": assessment.missing_fields},
        )
        self.db.commit()

    def _fail_run(self, run: Run, code: str, message: str) -> None:
        logger.error(
            "run_failed",
            extra={
                "run_id": run.id,
                "project_id": run.project_id,
                "stage": run.current_stage,
                "status": code,
            },
        )
        run.status = RunStatus.FAILED.value
        run.error_code = code
        run.error_message = message
        project = self.db.get(Project, run.project_id)
        if project and project.latest_version_id:
            project.status = ProjectStatus.READY.value
        elif project:
            project.status = ProjectStatus.DRAFT.value
        if project and project.active_write_run_id == run.id:
            project.active_write_run_id = None
        self._record_event_once(
            run,
            "run.failed",
            message,
            run.current_stage,
            {"code": code},
        )
        release_quota(self.db, run, run.current_stage)
        self._record_project_message_once(
            run,
            "system",
            "error",
            message,
            {"code": code},
        )
        self.db.commit()

    def _record_project_message_once(
        self,
        run: Run,
        role: str,
        message_type: str,
        content: str,
        payload: dict | None = None,
    ) -> None:
        existing = self.db.scalar(
            select(ProjectMessage.id).where(
                ProjectMessage.run_id == run.id,
                ProjectMessage.role == role,
                ProjectMessage.message_type == message_type,
            )
        )
        if existing is not None:
            return
        self.db.add(
            ProjectMessage(
                project_id=run.project_id,
                session_id=run.session_id,
                user_id=run.user_id,
                run_id=run.id,
                role=role,
                message_type=message_type,
                content=content,
                payload=payload or {},
            )
        )

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
