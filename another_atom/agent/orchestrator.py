import hashlib
import json
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from another_atom.agent.provider import (
    LLMProvider,
    LLMProviderError,
    get_llm_provider,
    requires_pm_clarification,
)
from another_atom.build.renderer import normalize_architecture_visual_tokens, validate_app_spec
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureDesign,
    ArchitectureDesignDraft,
    ArchitectureSpec,
    ArtifactType,
    BaseSourceSnapshot,
    Blueprint,
    BuildArtifact,
    BuildStatus,
    ChangeBrief,
    DataProfile,
    EngineerOutput,
    ExecutionReport,
    ExecutionRequest,
    ExecutionResult,
    HumanTaskKind,
    HumanTaskStatus,
    Mode,
    PMRequirementAssessment,
    PreviousFailureContext,
    ProductSpec,
    ProjectStatus,
    RequirementDelta,
    ReviewReport,
    RunStatus,
    SourceBundle,
    SourceContext,
    SourcePatchSet,
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
    SourcePatchError,
    apply_source_patch_set,
    build_source_context,
    build_source_snapshot,
    calculate_source_diff_from_files,
    commit_version,
    write_architecture_design,
    write_product_spec,
)
from another_atom.runtime.artifacts import (
    create_architecture_design,
    create_source_bundle,
    create_source_bundle_from_files,
)
from another_atom.runtime.client import RuntimeExecutorError, execute_request
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

_PROVIDER_EVENT_MESSAGES = {
    "provider.request.started": "Provider request started",
    "provider.first_token": "Provider returned the first token",
    "provider.progress": "Provider is still generating output",
    "provider.timeout": "Provider request timed out",
    "provider.fallback.started": "Fallback provider request started",
    "provider.primary.skipped": "Primary provider skipped while circuit is open",
    "provider.circuit.opened": "Primary provider circuit opened after timeout",
    "provider.response.received": "Provider response received",
    "provider.contract_correction.started": "Provider is correcting structured output",
    "provider.deadline.exceeded": "Agent stage deadline exceeded",
    "agent.message.started": "Agent response started",
    "agent.message.delta": "Agent response updated",
    "agent.message.completed": "Agent response completed",
    "agent.message.failed": "Agent response interrupted",
    "agent.output.delta": "Agent model output updated",
}


def _contains_chinese(value: str) -> bool:
    return any("\u3400" <= character <= "\u9fff" for character in value)


_LOCAL_SERVICE_TERMS = (
    "localhost",
    "127.0.0.1",
    "::1",
    "本地大模型",
    "本地模型",
    "local model",
    "ollama",
    "llama.cpp",
)


def _enforce_network_capability_policy(prompt: str, blueprint: Blueprint) -> Blueprint:
    normalized_prompt = prompt.casefold()
    if not any(term in normalized_prompt for term in _LOCAL_SERVICE_TERMS):
        return blueprint
    mapped: list[str] = []
    omitted = list(blueprint.omitted_requirements)
    for requirement in blueprint.mapped_requirements:
        if any(term in requirement.casefold() for term in _LOCAL_SERVICE_TERMS):
            if requirement not in omitted:
                omitted.append(requirement)
        else:
            mapped.append(requirement)
    chinese = _contains_chinese(prompt)
    boundary = (
        "不支持访问 localhost、loopback 或用户设备上的本地模型服务"
        if chinese
        else "localhost, loopback, and on-device model services are not supported"
    )
    if boundary not in omitted:
        omitted.append(boundary)
    reason = (
        "当前 Web Runtime 允许公网 API，但禁止访问 localhost 和用户设备本地服务。"
        if chinese
        else "The Web Runtime allows public APIs but blocks localhost and on-device services."
    )
    reasons = [item for item in blueprint.support_reasons if item != reason]
    reasons.append(reason)
    return blueprint.model_copy(
        update={
            "support_level": SupportLevel.ADAPTED,
            "support_reasons": reasons[:8],
            "mapped_requirements": mapped[:12],
            "omitted_requirements": omitted[:12],
        }
    )


def render_product_spec(prompt: str, blueprint: Blueprint) -> ProductSpec:
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

    def _provider_event_handler(
        self,
        run_id: str,
        stage: str,
    ) -> Callable[[str, dict], None]:
        def handle(event_type: str, payload: dict) -> None:
            if event_type not in _PROVIDER_EVENT_MESSAGES:
                return
            current = self.db.get(Run, run_id)
            if current is None:
                return
            if event_type.startswith("agent.message.") or event_type.startswith(
                "agent.output."
            ):
                self._persist_agent_message_event(current, stage, event_type, payload)
            record_event(
                self.db,
                run_id,
                event_type,
                _PROVIDER_EVENT_MESSAGES[event_type],
                stage=stage,
                payload=payload,
            )
            self.db.commit()

        return handle

    def _persist_agent_message_event(
        self,
        run: Run,
        stage: str,
        event_type: str,
        payload: dict,
    ) -> None:
        message_id = payload.get("message_id")
        if not isinstance(message_id, str) or not message_id:
            return
        message = self.db.get(ProjectMessage, message_id)
        if event_type == "agent.message.started":
            if message is not None:
                return
            provider_role = str(payload.get("role") or stage)
            message = ProjectMessage(
                id=message_id,
                project_id=run.project_id,
                session_id=run.session_id,
                user_id=run.user_id,
                run_id=run.id,
                role=self._project_message_role(provider_role, stage),
                message_type="agent_update",
                content="",
                payload={
                    "status": "streaming",
                    "stage": stage,
                    "provider_role": provider_role,
                },
            )
            self.db.add(message)
            return
        if message is None:
            return
        if event_type == "agent.message.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                message.content = f"{message.content}{delta}"
            return
        if event_type == "agent.output.delta":
            delta = payload.get("delta")
            if isinstance(delta, str) and delta:
                next_payload = dict(message.payload or {})
                current_output = next_payload.get("model_output")
                next_payload["model_output"] = (
                    f"{current_output if isinstance(current_output, str) else ''}{delta}"
                )
                message.payload = next_payload
            return
        next_payload = dict(message.payload or {})
        next_payload["status"] = (
            "completed" if event_type == "agent.message.completed" else "failed"
        )
        if event_type == "agent.message.failed" and payload.get("reason"):
            next_payload["reason"] = payload["reason"]
        message.payload = next_payload

    @staticmethod
    def _project_message_role(provider_role: str, stage: str) -> str:
        normalized = f"{provider_role} {stage}".casefold()
        if "product" in normalized or stage == "product_manager":
            return "product_manager"
        if "architect" in normalized or stage == "architect":
            return "architect"
        if "engineer" in normalized or stage in {"engineer", "engineer_repair"}:
            return "engineer"
        if "lead" in normalized:
            return "lead"
        return "system"

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
            blueprint = _enforce_network_capability_policy(effective_prompt, blueprint)
            artifact.payload = blueprint.model_dump(mode="json")
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
            product_spec = render_product_spec(effective_prompt, blueprint)
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
            else:
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

    def regenerate_product_spec(
        self,
        run: Run,
        instruction: str,
        current_product_spec: ProductSpec,
    ) -> tuple[Blueprint, ProductSpec, Artifact]:
        pending_task = self.db.scalar(
            select(HumanTask).where(
                HumanTask.run_id == run.id,
                HumanTask.user_id == run.user_id,
                HumanTask.kind == HumanTaskKind.APPROVAL.value,
                HumanTask.status == HumanTaskStatus.PENDING.value,
            )
        )
        if run.status != RunStatus.AWAITING_APPROVAL.value or pending_task is None:
            raise AppError(
                "PRODUCT_SPEC_UPDATE_NOT_ALLOWED",
                "This run is not waiting for ProductSpec approval",
                409,
            )
        run_claimed = self.db.execute(
            update(Run)
            .where(
                Run.id == run.id,
                Run.user_id == run.user_id,
                Run.status == RunStatus.AWAITING_APPROVAL.value,
            )
            .values(
                status=RunStatus.PRODUCT_RUNNING.value,
                current_stage="product_manager",
            )
            .execution_options(synchronize_session=False)
        )
        task_claimed = self.db.execute(
            update(HumanTask)
            .where(
                HumanTask.id == pending_task.id,
                HumanTask.user_id == run.user_id,
                HumanTask.status == HumanTaskStatus.PENDING.value,
            )
            .values(
                status=HumanTaskStatus.STALE.value,
                resolved_at=func.now(),
            )
            .execution_options(synchronize_session=False)
        )
        if run_claimed.rowcount != 1 or task_claimed.rowcount != 1:
            self.db.rollback()
            raise AppError(
                "PRODUCT_SPEC_UPDATE_NOT_ALLOWED",
                "The ProductSpec approval state changed; refresh before revising",
                409,
            )
        self.db.expire_all()
        run = self.db.get(Run, run.id)
        if run is None:
            self.db.rollback()
            raise AppError("RUN_NOT_FOUND", "Run was not found", 404)
        self.db.add(
            ProjectMessage(
                project_id=run.project_id,
                session_id=run.session_id,
                user_id=run.user_id,
                run_id=run.id,
                role="user",
                message_type="request",
                content=instruction,
                payload={"target": "product_spec", "action": "regenerate"},
            )
        )
        record_event(
            self.db,
            run.id,
            "product_spec.regeneration_started",
            "Product Manager is revising the ProductSpec from the current document",
            stage="product_manager",
            payload={"previous_content_hash": current_product_spec.content_hash},
        )
        self.db.commit()
        revision_prompt = (
            f"{run.prompt}\n\n"
            "已有产品说明如下。请保留未被修改要求影响的内容，只调整用户明确要求的部分。\n\n"
            f"{current_product_spec.content}\n\n"
            f"用户本次修改要求：\n{instruction}"
        )
        try:
            blueprint = self._run_unpersisted_agent_stage(
                run,
                "product_manager",
                lambda: self._create_blueprint_in_request_language(
                    run,
                    revision_prompt,
                    Mode(run.mode),
                ),
            )
            blueprint = _enforce_network_capability_policy(run.prompt, blueprint)
            product_spec = render_product_spec(run.prompt, blueprint)
            write_product_spec(run.project_id, product_spec.content)
            save_artifact(self.db, run.id, ArtifactType.BLUEPRINT, blueprint)
            artifact = save_artifact(
                self.db,
                run.id,
                ArtifactType.PRODUCT_SPEC,
                product_spec,
            )
            project = self.db.get(Project, run.project_id)
            if project is not None:
                project.name = blueprint.project_name
            run.status = RunStatus.AWAITING_APPROVAL.value
            run.current_stage = "blueprint_approval"
            self._create_human_task(
                run,
                kind=HumanTaskKind.APPROVAL,
                stage="blueprint_approval",
                prompt="查看并确认重新生成的产品说明后继续构建",
                subject=f"product_spec:{artifact.id}:{product_spec.content_hash}",
                payload={
                    "artifact_id": artifact.id,
                    "artifact_type": ArtifactType.PRODUCT_SPEC.value,
                    "path": product_spec.path,
                    "content_hash": product_spec.content_hash,
                    "support_level": blueprint.support_level.value,
                    "previous_human_task_id": pending_task.id,
                },
            )
            record_event(
                self.db,
                run.id,
                "product_spec.regenerated",
                "Product specification was regenerated from the current document",
                stage="blueprint_approval",
                payload={
                    "artifact_id": artifact.id,
                    "content_hash": product_spec.content_hash,
                },
            )
            self.db.commit()
            return blueprint, product_spec, artifact
        except Exception:
            self.db.rollback()
            current = self.db.get(Run, run.id)
            if current is not None:
                current.status = RunStatus.AWAITING_APPROVAL.value
                current.current_stage = "blueprint_approval"
                previous_task = self.db.get(HumanTask, pending_task.id)
                if previous_task is not None:
                    previous_task.status = HumanTaskStatus.PENDING.value
                    previous_task.resolved_at = None
                record_event(
                    self.db,
                    current.id,
                    "product_spec.regeneration_failed",
                    "Product specification regeneration failed; the previous document is retained",
                    stage="blueprint_approval",
                    payload={"content_hash": current_product_spec.content_hash},
                )
                self.db.commit()
            raise

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
        product_spec_artifact = get_artifact(self.db, run.id, ArtifactType.PRODUCT_SPEC)
        if project is None or blueprint_artifact is None or product_spec_artifact is None:
            self._fail_run(run, "MISSING_INPUT", "Approved ProductSpec could not be loaded")
            return

        blueprint = Blueprint.model_validate(blueprint_artifact.payload)
        product_spec = ProductSpec.model_validate(product_spec_artifact.payload)
        try:
            logger.info(
                "build_pipeline_started",
                extra={"run_id": run.id, "project_id": run.project_id},
            )
            project.status = ProjectStatus.BUILDING.value
            architecture_design = self._run_architect(run, blueprint, product_spec)
            if architecture_design is None:
                return
            app_spec, source_bundle = self._run_engineer(
                run, blueprint, product_spec, architecture_design
            )
            execution_result, build_job = self._run_build(
                run,
                project,
                blueprint,
                product_spec,
                architecture_design,
                app_spec,
                source_bundle,
                attempt=1,
            )
            validation_report = execution_result.validation_report
            if not validation_report.passed and self._can_auto_repair(validation_report):
                app_spec = self._run_engineer_repair(
                    run,
                    blueprint,
                    architecture_design.visual_tokens,
                    app_spec,
                    validation_report,
                )
                prior_tests = [
                    item.model_dump(mode="python", exclude={"content_hash"})
                    for item in source_bundle.files
                    if item.role == "test"
                ]
                source_bundle = create_source_bundle(
                    EngineerOutput(app_spec=app_spec, unit_tests=prior_tests),
                    blueprint.product_type,
                )
                execution_result, build_job = self._run_build(
                    run,
                    project,
                    blueprint,
                    product_spec,
                    architecture_design,
                    app_spec,
                    source_bundle,
                    attempt=2,
                )
                validation_report = execution_result.validation_report
                save_artifact(
                    self.db,
                    run.id,
                    ArtifactType.REPAIR_VALIDATION_REPORT,
                    validation_report,
                )
                self._record_event_once(
                    run,
                    "repair.validation_completed",
                    "The revised SourceBundle completed build, unit tests, and validation",
                    "build",
                    {"passed": validation_report.passed, "repair_attempt": 1},
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

            compatibility_review = ReviewReport(
                summary=(
                    "兼容字段：V1 当前由独立 Runtime（运行时）的构建、单元测试和确定性验证"
                    "作为发布前证据，不再调用 Reviewer（评审员）Agent。"
                ),
                requirement_checks=["ProductSpec 与 ArchitectureDesign 已进入执行请求。"],
                engineering_checks=["node --check、node --test 和确定性校验均已通过。"],
                suggested_actions=["accept"],
                reviewer_mode="deterministic_only",
            )
            version = self._create_version(
                run,
                project,
                app_spec,
                None,
                validation_report.model_dump(mode="json"),
                compatibility_review.model_dump(mode="json"),
                VersionSource.BUILD,
                architecture_design=architecture_design,
                source_bundle=source_bundle,
                execution_report=execution_result.execution_report,
                build_artifact=execution_result.build_artifact,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = RunStatus.COMPLETED.value
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
        except RuntimeExecutorError as exc:
            logger.warning(
                "runtime_executor_failed",
                extra={"run_id": run.id, "stage": run.current_stage},
            )
            self._fail_run(run, "RUNTIME_EXECUTOR_UNAVAILABLE", str(exc))

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
        source_architecture_design = get_artifact(
            self.db, base_version.run_id, ArtifactType.ARCHITECTURE_DESIGN
        )
        base_architecture_design = (
            ArchitectureDesign.model_validate(source_architecture_design.payload)
            if source_architecture_design is not None
            else None
        )
        product_spec = self._product_spec_for_version(base_version)
        if product_spec is None:
            self._fail_run(run, "MISSING_INPUT", "The current ProductSpec could not be loaded")
            return
        if get_artifact(self.db, run.id, ArtifactType.PRODUCT_SPEC) is None:
            save_artifact(self.db, run.id, ArtifactType.PRODUCT_SPEC, product_spec)
            self.db.commit()

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
            if base_architecture_design is not None:
                architecture_draft = self._run_unpersisted_agent_stage(
                    run,
                    "architect_design_revision",
                    lambda: self._provider(run).revise_architecture_design(
                        product_spec,
                        blueprint,
                        base_architecture_design,
                        architecture_spec,
                        change_brief,
                        requirement_delta,
                    ),
                )
            else:
                architecture_draft = self._run_unpersisted_agent_stage(
                    run,
                    "architect_design_migration",
                    lambda: self._provider(run).create_architecture_design(
                        product_spec, blueprint
                    ),
                )
            architecture_draft = architecture_draft.model_copy(
                update={"visual_tokens": architecture_spec}
            )
            architecture_design = create_architecture_design(
                architecture_draft, product_spec.content_hash
            )
            write_architecture_design(run.project_id, architecture_design.content)
            save_artifact(
                self.db,
                run.id,
                ArtifactType.ARCHITECTURE_DESIGN,
                architecture_design,
            )
            self._record_event_once(
                run,
                "architecture.design_revised",
                "ArchitectureDesign was synchronized with the approved change",
                "architect",
                {"content_hash": architecture_design.content_hash},
            )
            self.db.commit()

            source_context_artifact = get_artifact(
                self.db, run.id, ArtifactType.SOURCE_CONTEXT
            )
            if source_context_artifact:
                source_context = SourceContext.model_validate(source_context_artifact.payload)
            else:
                source_context = build_source_context(
                    source_snapshot,
                    effective_prompt,
                    get_settings().max_source_chars,
                    self._selected_files_for_run(run),
                    ["app-spec.json"],
                )
                source_context_artifact = save_artifact(
                    self.db, run.id, ArtifactType.SOURCE_CONTEXT, source_context
                )
            self._record_event_once(
                run,
                "source.context_prepared",
                "Runtime prepared the deterministic source Context",
                "engineer",
                {
                    "max_source_chars": source_context.max_source_chars,
                    "used_source_chars": source_context.used_source_chars,
                    "included_files": [item.path for item in source_context.included_files],
                    "omitted_files": source_context.omitted_files,
                    "trimming_applied": source_context.trimming_applied,
                },
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
            patch_artifact = get_artifact(
                self.db, run.id, ArtifactType.SOURCE_PATCH_SET
            )
            if patch_artifact is not None:
                patch_set = SourcePatchSet.model_validate(patch_artifact.payload)
            else:
                patch_set, patch_artifact, _ = self._run_agent_stage(
                    run,
                    "engineer",
                    ArtifactType.SOURCE_PATCH_SET,
                    SourcePatchSet,
                    lambda: self._provider(run).create_source_patch_set(
                        run.id,
                        source_snapshot,
                        source_context,
                        product_spec,
                        blueprint,
                        architecture_design,
                        architecture_spec,
                        change_brief,
                        requirement_delta,
                        base_app_spec,
                    ),
                )
            if patch_set.run_id != run.id:
                raise AppError(
                    "PATCH_BASE_MISMATCH",
                    "SourcePatchSet does not match the active Run",
                    422,
                )
            self._record_event_once(
                run,
                "source.patch_created",
                "Engineer produced a baseline-bound SourcePatchSet",
                "engineer",
                {
                    "artifact_id": patch_artifact.id,
                    "patch_files": [item.path for item in patch_set.patches],
                },
            )
            self._record_event_once(
                run,
                "source.patch_check_started",
                "Runtime is validating and checking the SourcePatchSet",
                "engineer",
                {"patch_count": len(patch_set.patches)},
            )
            self.db.commit()
            try:
                app_spec, candidate_files, apply_report = apply_source_patch_set(
                    source_snapshot,
                    source_context,
                    patch_set,
                    base_app_spec,
                    architecture_spec,
                )
            except SourcePatchError as exc:
                self._record_event_once(
                    run,
                    "source.patch_failed",
                    str(exc),
                    "engineer",
                    {"error_code": exc.code},
                )
                self.db.commit()
                raise AppError(exc.code, str(exc), 422) from exc
            source_bundle = create_source_bundle_from_files(
                candidate_files, blueprint.product_type
            )
            source_diff = calculate_source_diff_from_files(
                source_snapshot, candidate_files
            )
            save_artifact(self.db, run.id, ArtifactType.APP_SPEC, app_spec)
            save_artifact(
                self.db, run.id, ArtifactType.SOURCE_BUNDLE, source_bundle
            )
            save_artifact(self.db, run.id, ArtifactType.SOURCE_DIFF, source_diff)
            apply_artifact = save_artifact(
                self.db,
                run.id,
                ArtifactType.SOURCE_PATCH_APPLY_REPORT,
                apply_report,
            )
            self._record_event_once(
                run,
                "source.patch_applied",
                "Runtime applied the SourcePatchSet in an isolated candidate workspace",
                "engineer",
                {
                    "artifact_id": apply_artifact.id,
                    "applied_files": apply_report.applied_files,
                    "candidate_source_hash": apply_report.candidate_source_hash,
                },
            )
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
            self._record_event_once(
                run,
                "stage.completed",
                "SourcePatchSet passed local apply and candidate Contract validation",
                "engineer",
                {
                    "artifact_id": patch_artifact.id,
                    "source_context_artifact_id": source_context_artifact.id,
                    "source_trimming_applied": source_context.trimming_applied,
                },
            )
            self.db.commit()

            execution_result, build_job = self._run_build(
                run,
                project,
                blueprint,
                product_spec,
                architecture_design,
                app_spec,
                source_bundle,
                attempt=1,
            )
            validation_report = execution_result.validation_report
            if not validation_report.passed:
                build_job.status = BuildStatus.FAILED.value
                self._fail_run(
                    run,
                    "BUILD_VALIDATION_FAILED",
                    "The Web source validator rejected the applied SourcePatchSet",
                )
                return
            compatibility_review = ReviewReport(
                summary=(
                    "兼容字段：本次修改由独立 Runtime（运行时）的构建、单元测试和确定性验证"
                    "提供发布前证据，未调用 Data Analyst（数据分析师）或 Reviewer（评审员）Agent。"
                ),
                engineering_checks=["node --check、node --test 和确定性校验均已通过。"],
                suggested_actions=["accept"],
                reviewer_mode="deterministic_only",
            )
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
                None,
                validation_report.model_dump(mode="json"),
                compatibility_review.model_dump(mode="json"),
                VersionSource.AI_EDIT,
                architecture_design=architecture_design,
                source_bundle=source_bundle,
                execution_report=execution_result.execution_report,
                build_artifact=execution_result.build_artifact,
            )
            build_job.status = BuildStatus.SUCCEEDED.value
            run.status = RunStatus.COMPLETED.value
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

    def _run_architect(
        self,
        run: Run,
        blueprint: Blueprint,
        product_spec: ProductSpec,
    ) -> ArchitectureDesign | None:
        run.status = RunStatus.ARCHITECT_RUNNING.value
        run.current_stage = "architect"
        self._record_event_once(
            run,
            "stage.started",
            "Architect is producing the ArchitectureDesign document",
            "architect",
        )
        existing = get_artifact(self.db, run.id, ArtifactType.ARCHITECTURE_DESIGN)
        if existing is not None:
            architecture_design = ArchitectureDesign.model_validate(existing.payload)
            artifact = existing
        else:
            draft = self._run_unpersisted_agent_stage(
                run,
                "architect",
                lambda: self._provider(run).create_architecture_design(
                    product_spec, blueprint
                ),
            )
            draft = ArchitectureDesignDraft.model_validate(draft).model_copy(
                update={
                    "visual_tokens": normalize_architecture_visual_tokens(
                        draft.visual_tokens
                    )
                }
            )
            architecture_design = create_architecture_design(
                draft, product_spec.content_hash
            )
            write_architecture_design(run.project_id, architecture_design.content)
            artifact = save_artifact(
                self.db,
                run.id,
                ArtifactType.ARCHITECTURE_DESIGN,
                architecture_design,
            )
            save_artifact(
                self.db,
                run.id,
                ArtifactType.ARCHITECTURE_SPEC,
                architecture_design.visual_tokens,
            )
        self._record_event_once(
            run,
            "stage.completed",
            "ArchitectureDesign was written and passed contract validation",
            "architect",
            {
                "artifact_id": artifact.id,
                "path": architecture_design.path,
                "requires_product_reapproval": (
                    architecture_design.requires_product_reapproval
                ),
            },
        )
        self.db.commit()
        if architecture_design.requires_product_reapproval:
            reason = architecture_design.reapproval_reason or "架构设计改变了产品边界。"
            self._pause_for_input(
                run,
                PMRequirementAssessment(
                    outcome="needs_input",
                    summary=reason,
                    question=(
                        f"架构设计发现必须调整已确认的产品规格：{reason}。"
                        "请确认新的产品边界或补充替代要求。"
                    ),
                    missing_fields=["product_boundary_reapproval"],
                ),
                self._effective_prompt(run),
            )
            return None
        return architecture_design

    def _run_engineer(
        self,
        run: Run,
        blueprint: Blueprint,
        product_spec: ProductSpec,
        architecture_design: ArchitectureDesign,
    ) -> tuple[AppSpec, SourceBundle]:
        run.status = RunStatus.ENGINEER_RUNNING.value
        run.current_stage = "engineer"
        self._record_event_once(
            run,
            "stage.started",
            "Engineer is generating source code and unit tests",
            "engineer",
        )
        self._record_event_once(
            run,
            "engineer.context.prepared",
            "Engineer context is ready from ProductSpec and ArchitectureDesign",
            "engineer",
            {"inputs": ["product_spec", "architecture_design", "blueprint", "request"]},
        )
        app_artifact = get_artifact(self.db, run.id, ArtifactType.APP_SPEC)
        source_artifact = get_artifact(self.db, run.id, ArtifactType.SOURCE_BUNDLE)
        if app_artifact is not None and source_artifact is not None:
            app_spec = AppSpec.model_validate(app_artifact.payload)
            source_bundle = SourceBundle.model_validate(source_artifact.payload)
            artifact = app_artifact
        else:
            output = self._run_unpersisted_agent_stage(
                run,
                "engineer",
                lambda: self._provider(run).create_engineer_output(
                    product_spec,
                    architecture_design,
                    blueprint,
                    run.prompt,
                ),
            )
            output = EngineerOutput.model_validate(output)
            app_spec = self._align_app_spec_visual_tokens(
                output.app_spec, architecture_design.visual_tokens
            )
            output = output.model_copy(update={"app_spec": app_spec})
            source_bundle = create_source_bundle(output, blueprint.product_type)
            artifact = save_artifact(self.db, run.id, ArtifactType.APP_SPEC, app_spec)
            save_artifact(self.db, run.id, ArtifactType.SOURCE_BUNDLE, source_bundle)
        self._record_event_once(
            run,
            "stage.completed",
            "SourceBundle and Engineer unit tests passed contract validation",
            "engineer",
            {
                "artifact_id": artifact.id,
                "source_manifest_hash": source_bundle.manifest_hash,
                "test_files": [
                    item.path for item in source_bundle.files if item.role == "test"
                ],
            },
        )
        self.db.commit()
        return app_spec, source_bundle

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
        self._record_event_once(
            run,
            "engineer.repair_context.prepared",
            "Engineer repair context is ready with deterministic validation evidence",
            "engineer",
            {
                "inputs": ["blueprint", "architecture_spec", "app_spec", "validation_report"],
                "failed_check_ids": failed_check_ids,
                "repair_attempt": 1,
            },
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
        product_spec: ProductSpec,
        architecture_design: ArchitectureDesign,
        app_spec: AppSpec,
        source_bundle: SourceBundle,
        *,
        attempt: int,
    ) -> tuple[ExecutionResult, BuildJob]:
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
        build_job.status = BuildStatus.DISPATCHING.value
        self._record_event_once(
            run,
            "build.started",
            "SourceBundle was dispatched to the independent Runtime Executor",
            "build",
            {"build_job_id": build_job.id, "attempt": attempt},
        )
        request_payload = {
            "execution_id": f"{run.id}-{attempt}",
            "run_id": run.id,
            "attempt": attempt,
            "adapter_id": source_bundle.adapter_id,
            "product_spec_hash": product_spec.content_hash,
            "architecture_design_hash": architecture_design.content_hash,
            "source_manifest_hash": source_bundle.manifest_hash,
            "prompt": run.prompt,
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
        execution_request = ExecutionRequest(
            **request_payload,
            request_hash=request_hash,
        )
        events, execution_result = execute_request(execution_request)
        for execution_event in events:
            status_map = {
                "source.materializing": BuildStatus.MATERIALIZING.value,
                "build.started": BuildStatus.BUILDING.value,
                "test.started": BuildStatus.TESTING.value,
                "validation.started": BuildStatus.VALIDATING.value,
            }
            if execution_event.type in status_map:
                build_job.status = status_map[execution_event.type]
            record_event(
                self.db,
                run.id,
                f"executor.{execution_event.type}",
                f"Runtime Executor: {execution_event.type}",
                stage="build",
                payload=execution_event.payload,
            )
        save_artifact(
            self.db,
            run.id,
            ArtifactType.EXECUTION_REPORT,
            execution_result.execution_report,
        )
        save_artifact(
            self.db,
            run.id,
            ArtifactType.VALIDATION_REPORT,
            execution_result.validation_report,
        )
        if execution_result.build_artifact is not None:
            save_artifact(
                self.db,
                run.id,
                ArtifactType.BUILD_ARTIFACT,
                execution_result.build_artifact,
            )
        save_artifact(self.db, run.id, ArtifactType.SOURCE_BUNDLE, source_bundle)
        self.db.commit()
        return execution_result, build_job

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
        data_profile: dict | None,
        validation_report: dict,
        review_report: dict,
        source: VersionSource,
        *,
        architecture_design: ArchitectureDesign | None = None,
        source_bundle: SourceBundle | None = None,
        execution_report: ExecutionReport | None = None,
        build_artifact: BuildArtifact | None = None,
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
            architecture_design=(
                architecture_design.model_dump(mode="json")
                if architecture_design is not None
                else None
            ),
            source_bundle=(
                source_bundle.model_dump(mode="json")
                if source_bundle is not None
                else None
            ),
            execution_report=(
                execution_report.model_dump(mode="json")
                if execution_report is not None
                else None
            ),
            build_artifact=(
                build_artifact.model_dump(mode="json")
                if build_artifact is not None
                else None
            ),
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
            source_bundle,
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

    def _selected_files_for_run(self, run: Run) -> list[str]:
        message = self.db.scalar(
            select(ProjectMessage)
            .where(
                ProjectMessage.run_id == run.id,
                ProjectMessage.role == "user",
                ProjectMessage.message_type == "request",
            )
            .order_by(ProjectMessage.created_at.asc(), ProjectMessage.id.asc())
            .limit(1)
        )
        if message is None:
            return []
        selected_files = message.payload.get("selected_files", [])
        return [item for item in selected_files if isinstance(item, str)]

    def _product_spec_for_version(self, version: ProjectVersion) -> ProductSpec | None:
        current: ProjectVersion | None = version
        visited: set[str] = set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            artifact = get_artifact(self.db, current.run_id, ArtifactType.PRODUCT_SPEC)
            if artifact is not None:
                return ProductSpec.model_validate(artifact.payload)
            version_run = self.db.get(Run, current.run_id)
            current = (
                self.db.get(ProjectVersion, version_run.base_version_id)
                if version_run is not None and version_run.base_version_id
                else None
            )
        return None

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
        provider = self._provider(run)
        provider.begin_stage(
            timeout_seconds=get_settings().agent_stage_timeout_seconds,
            event_handler=self._provider_event_handler(run.id, stage),
        )
        try:
            return self._run_active_agent_stage(
                run,
                stage,
                artifact_type,
                model_type,
                operation,
                provider,
                max_attempts,
            )
        finally:
            provider.end_stage()

    def _run_active_agent_stage(
        self,
        run: Run,
        stage: str,
        artifact_type: ArtifactType,
        model_type: type[T],
        operation: Callable[[], T],
        provider: LLMProvider,
        max_attempts: int,
    ) -> tuple[T, Artifact, bool]:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            reserved_units = provider.reservation_units
            reserve_quota(self.db, run.user_id, run, stage, reserved_units)
            record_event(
                self.db,
                run.id,
                "agent.attempt.started",
                "Agent model attempt started",
                stage=stage,
                payload={"attempt": attempt, "max_attempts": max_attempts},
            )
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
                record_event(
                    self.db,
                    run.id,
                    "agent.output.validated",
                    "Agent output passed Contract validation",
                    stage=stage,
                    payload={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "artifact_type": artifact_type.value,
                    },
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
                failure_kind, failure_summary = self._agent_attempt_failure(exc)
                will_retry = attempt < max_attempts
                record_event(
                    self.db,
                    run.id,
                    "agent.retry",
                    (
                        "Agent attempt failed; retrying"
                        if will_retry
                        else "Agent attempt failed; retry budget exhausted"
                    ),
                    stage=stage,
                    payload={
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "will_retry": will_retry,
                        "failure_kind": failure_kind,
                        "failure_summary": failure_summary,
                    },
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

    @staticmethod
    def _agent_attempt_failure(exc: Exception) -> tuple[str, str]:
        detail = " ".join(str(exc).split())[:500]
        lowered = detail.casefold()
        if "timed out" in lowered or "timeout" in lowered:
            return "provider_timeout", detail
        if "api_key" in lowered or "api key" in lowered:
            return "provider_configuration", detail
        if (
            "validation error" in lowered
            or "structured response" in lowered
            or "json object" in lowered
        ):
            return "contract_validation", detail
        if "response" in lowered and ("empty" in lowered or "chat message" in lowered):
            return "provider_response", detail
        if isinstance(exc, LLMProviderError):
            return "provider_error", detail
        return "contract_validation", detail

    def _run_unpersisted_agent_stage(
        self,
        run: Run,
        stage: str,
        operation: Callable[[], T],
        max_attempts: int = 3,
    ) -> T:
        provider = self._provider(run)
        provider.begin_stage(
            timeout_seconds=get_settings().agent_stage_timeout_seconds,
            event_handler=self._provider_event_handler(run.id, stage),
        )
        try:
            return self._run_active_unpersisted_agent_stage(
                run,
                stage,
                operation,
                provider,
                max_attempts,
            )
        finally:
            provider.end_stage()

    def _run_active_unpersisted_agent_stage(
        self,
        run: Run,
        stage: str,
        operation: Callable[[], T],
        provider: LLMProvider,
        max_attempts: int,
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            reserved_units = provider.reservation_units
            reserve_quota(self.db, run.user_id, run, stage, reserved_units)
            record_event(
                self.db,
                run.id,
                "agent.attempt.started",
                "Agent model attempt started",
                stage=stage,
                payload={"attempt": attempt, "max_attempts": max_attempts},
            )
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
                record_event(
                    self.db,
                    run.id,
                    "agent.output.validated",
                    "Agent output passed Contract validation",
                    stage=stage,
                    payload={"attempt": attempt, "max_attempts": max_attempts},
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
