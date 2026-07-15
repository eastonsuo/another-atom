from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Mode(StrEnum):
    ENGINEER = "engineer"
    TEAM = "team"


class LeadRoute(StrEnum):
    DIRECT = "direct"
    CLARIFY = "clarify"
    TEAM = "team"


class ProjectLeadIntent(StrEnum):
    ANSWER = "answer"
    CLARIFY = "clarify"
    PROPOSE_CHANGE = "propose_change"


class SupportLevel(StrEnum):
    SUPPORTED = "supported"
    ADAPTED = "adapted"
    UNSUPPORTED = "unsupported"


class RunStatus(StrEnum):
    PRODUCT_RUNNING = "product_running"
    AWAITING_APPROVAL = "awaiting_approval"
    ARCHITECT_RUNNING = "architect_running"
    ENGINEER_RUNNING = "engineer_running"
    BUILD_QUEUED = "build_queued"
    BUILDING = "building"
    DATA_RUNNING = "data_running"
    REVIEW_RUNNING = "review_running"
    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HumanTaskKind(StrEnum):
    INPUT_REQUEST = "input_request"
    APPROVAL = "approval"


class HumanTaskStatus(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STALE = "stale"


class BuildStatus(StrEnum):
    QUEUED = "queued"
    WAITING_INPUT = "waiting_input"
    DISPATCHING = "dispatching"
    MATERIALIZING = "materializing"
    BUILDING = "building"
    TESTING = "testing"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    BUILDING = "building"
    READY = "ready"
    LIVE = "live"
    PAUSED = "paused"


class ArtifactType(StrEnum):
    CHANGE_BRIEF = "change_brief"
    REQUIREMENT_DELTA = "requirement_delta"
    BASE_SOURCE_SNAPSHOT = "base_source_snapshot"
    SOURCE_CONTEXT = "source_context"
    SOURCE_PATCH_SET = "source_patch_set"
    SOURCE_PATCH_APPLY_REPORT = "source_patch_apply_report"
    SOURCE_FILE_CHANGE_SET = "source_file_change_set"
    SOURCE_CHANGE_APPLY_REPORT = "source_change_apply_report"
    SOURCE_DIFF = "source_diff"
    BLUEPRINT = "blueprint"
    PRODUCT_SPEC = "product_spec"
    ARCHITECTURE_DESIGN = "architecture_design"
    ARCHITECTURE_SPEC = "architecture_spec"
    APP_SPEC = "app_spec"
    APP_SPEC_REPAIR = "app_spec_repair"
    ENGINEER_OUTPUT_REPAIR = "engineer_output_repair"
    SOURCE_BUNDLE = "source_bundle"
    BUILD_ARTIFACT = "build_artifact"
    EXECUTION_REPORT = "execution_report"
    DATA_PROFILE = "data_profile"
    VALIDATION_REPORT = "validation_report"
    REPAIR_VALIDATION_REPORT = "repair_validation_report"
    REVIEW_REPORT = "review_report"
    # Read-only compatibility for runs created before Reviewer became a role.
    DATA_REVIEW = "data_review"


class VersionSource(StrEnum):
    BUILD = "build"
    AI_EDIT = "ai_edit"
    EDIT = "edit"
    RESOLVE = "resolve"
    RESTORE = "restore"


class PublicationStrategy(StrEnum):
    ALWAYS_LATEST = "always_latest"
    SPECIFY_VERSION = "specify_version"


class AttachmentMeta(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=10_000_000)
    content_type: str = Field(default="application/octet-stream", max_length=100)


class Blueprint(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_name: str = Field(min_length=1, max_length=80)
    product_type: str = Field(default="web_application", min_length=1, max_length=80)
    support_level: SupportLevel
    support_reasons: list[str] = Field(default_factory=list, max_length=8)
    mapped_requirements: list[str] = Field(default_factory=list, max_length=12)
    omitted_requirements: list[str] = Field(default_factory=list, max_length=12)
    rewrite_suggestion: str | None = Field(default=None, max_length=500)
    capability_policy_version: Literal["catalog-v1", "web-v1"] = "web-v1"
    pages: list[str] = Field(min_length=1, max_length=12)
    modules: list[str] = Field(min_length=1, max_length=20)
    visual_direction: str = Field(min_length=1, max_length=240)
    data_requirements: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("pages", "modules")
    @classmethod
    def labels_are_not_blank(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("Blueprint page and module labels cannot be blank")
        return cleaned


class ProductSpec(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    path: Literal["docs/product-spec.md"] = "docs/product-spec.md"
    summary: str = Field(min_length=1, max_length=600)
    content: str = Field(min_length=1, max_length=30_000)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProductSpecUpdateRequest(BaseModel):
    summary: str | None = Field(default=None, min_length=1, max_length=600)
    instruction: str | None = Field(default=None, min_length=1, max_length=4000)
    action: Literal["save", "regenerate"]

    @model_validator(mode="after")
    def content_matches_action(self) -> ProductSpecUpdateRequest:
        if self.action == "save" and not self.summary:
            raise ValueError("Saving requires a summary")
        if self.action == "regenerate" and not (self.instruction or self.summary):
            raise ValueError("Regeneration requires an instruction or edited summary")
        return self


class PMRequirementAssessment(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    outcome: Literal["ready", "needs_input"]
    summary: str = Field(min_length=1, max_length=600)
    question: str | None = Field(default=None, max_length=500)
    missing_fields: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("PM clarification question cannot be blank")
        return value.strip() if value else None


class ArchitectureSpec(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    architecture_summary: str = Field(min_length=1, max_length=300)
    page_strategy: list[str] = Field(min_length=1, max_length=8)
    data_entities: list[str] = Field(min_length=1, max_length=8)
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    typography: Literal["sans", "serif"] = "sans"
    density: Literal["compact", "comfortable"] = "comfortable"
    style: str = Field(min_length=1, max_length=120)


class ArchitectureComponent(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    responsibility: str = Field(min_length=1, max_length=500)
    files: list[str] = Field(default_factory=list, max_length=20)


class ArchitectureDesignDraft(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: str = Field(min_length=1, max_length=600)
    target_platform: str = Field(min_length=1, max_length=120)
    runtime_adapter: str = Field(min_length=1, max_length=80)
    capability_gaps: list[str] = Field(default_factory=list, max_length=12)
    components: list[ArchitectureComponent] = Field(min_length=1, max_length=20)
    state_and_data_flow: list[str] = Field(min_length=1, max_length=20)
    interactions: list[str] = Field(min_length=1, max_length=20)
    interfaces: list[str] = Field(default_factory=list, max_length=20)
    directory_plan: list[str] = Field(min_length=1, max_length=30)
    test_strategy: list[str] = Field(min_length=1, max_length=20)
    acceptance_mapping: list[str] = Field(min_length=1, max_length=30)
    visual_tokens: ArchitectureSpec
    requires_product_reapproval: bool = False
    reapproval_reason: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def reapproval_reason_matches_flag(self) -> ArchitectureDesignDraft:
        if self.requires_product_reapproval and not (self.reapproval_reason or "").strip():
            raise ValueError("reapproval_reason is required when product reapproval is required")
        if not self.requires_product_reapproval and self.reapproval_reason is not None:
            self.reapproval_reason = None
        return self


class ArchitectureDesign(ArchitectureDesignDraft):
    path: Literal["docs/architecture-design.md"] = "docs/architecture-design.md"
    content: str = Field(min_length=1, max_length=60_000)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    product_spec_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ProductItem(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=60)
    price: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=300)
    image_url: str


class PageSpec(BaseModel):
    route: str = Field(pattern=r"^/[a-z0-9/_-]*$")
    name: str = Field(min_length=1, max_length=80)
    sections: list[str] = Field(min_length=1, max_length=10)


class AppSpec(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_name: str
    tagline: str = Field(min_length=1, max_length=160)
    hero_title: str = Field(min_length=1, max_length=120)
    hero_body: str = Field(min_length=1, max_length=300)
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    pages: list[PageSpec] = Field(min_length=1, max_length=12)
    products: list[ProductItem] = Field(default_factory=list, max_length=12)
    html: str = Field(default="", max_length=40_000)
    css: str = Field(default="", max_length=40_000)
    javascript: str = Field(default="", max_length=40_000)


class SourceFileDraft(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    role: Literal["source", "test", "config"]
    content: str = Field(max_length=120_000)

    @field_validator("path")
    @classmethod
    def path_is_relative_and_bounded(cls, value: str) -> str:
        normalized = value.strip()
        parts = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or "\\" in normalized
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("Source file path must be a normalized relative POSIX path")
        return normalized


class SourceFile(SourceFileDraft):
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class EngineerOutput(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    app_spec: AppSpec
    unit_tests: list[SourceFileDraft] = Field(min_length=1, max_length=8)

    @field_validator("unit_tests")
    @classmethod
    def tests_use_test_paths(cls, value: list[SourceFileDraft]) -> list[SourceFileDraft]:
        paths = set()
        for item in value:
            if item.role != "test" or not item.path.startswith("tests/"):
                raise ValueError("Engineer unit tests must use role=test under tests/")
            if not item.path.endswith(".test.js"):
                raise ValueError("web-static-v1 tests must end with .test.js")
            if item.path in paths:
                raise ValueError("Engineer unit test paths must be unique")
            paths.add(item.path)
        return value


class SourceBundle(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    adapter_id: Literal["web-static-v1"] = "web-static-v1"
    project_type: str = Field(min_length=1, max_length=80)
    entrypoint: Literal["index.html"] = "index.html"
    files: list[SourceFile] = Field(min_length=5, max_length=24)
    manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("files")
    @classmethod
    def file_paths_are_unique(cls, value: list[SourceFile]) -> list[SourceFile]:
        paths = [item.path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("SourceBundle file paths must be unique")
        if "index.html" not in paths or not any(item.role == "test" for item in value):
            raise ValueError("SourceBundle requires index.html and at least one test")
        return value


class PreviousFailureContext(BaseModel):
    run_id: str
    stage: str
    error_code: str | None = None
    error_message: str | None = None
    artifact_types: list[str] = Field(default_factory=list, max_length=20)


class ChangeBrief(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    original_request: str = Field(min_length=1, max_length=4000)
    goal: str = Field(min_length=1, max_length=800)
    preserve: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)
    previous_failure: PreviousFailureContext | None = None


class RequirementDelta(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    change_summary: str = Field(min_length=1, max_length=800)
    changed_requirements: list[str] = Field(min_length=1, max_length=20)
    preserved_requirements: list[str] = Field(default_factory=list, max_length=20)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


class SourceSnapshotFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    content: str


class BaseSourceSnapshot(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    base_version_id: str
    base_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    files: list[SourceSnapshotFile] = Field(min_length=1)
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class SourceContext(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_source_chars: int = Field(gt=0)
    used_source_chars: int = Field(ge=0)
    included_files: list[SourceSnapshotFile] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    runtime_managed_files: list[str] = Field(default_factory=list)
    trimming_applied: bool = False


class AppSpecDelta(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=160)
    tagline: str | None = Field(default=None, min_length=1, max_length=160)
    hero_title: str | None = Field(default=None, min_length=1, max_length=120)
    hero_body: str | None = Field(default=None, min_length=1, max_length=300)
    pages: list[PageSpec] | None = Field(default=None, min_length=1, max_length=12)
    products: list[ProductItem] | None = Field(default=None, max_length=12)


class SourceFileChange(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    operation: Literal["modify", "add", "delete"]
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    replacement_content: str | None = Field(default=None, max_length=120_000)

    @field_validator("path")
    @classmethod
    def path_is_normalized_relative_posix(cls, value: str) -> str:
        normalized = value.strip()
        parts = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or "\\" in normalized
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("Source change path must be a normalized relative POSIX path")
        return normalized

    @model_validator(mode="after")
    def content_and_hash_match_operation(self) -> SourceFileChange:
        if self.operation == "modify":
            if self.before_hash is None or self.replacement_content is None:
                raise ValueError("modify changes require before_hash and replacement_content")
        elif self.operation == "add":
            if self.before_hash is not None or self.replacement_content is None:
                raise ValueError("add changes require replacement_content without before_hash")
        elif self.before_hash is None or self.replacement_content is not None:
            raise ValueError("delete changes require before_hash without replacement_content")
        return self


class SourceFileChangeSet(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    base_version_id: str = Field(min_length=1, max_length=80)
    base_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=1, max_length=800)
    app_spec_delta: AppSpecDelta = Field(default_factory=AppSpecDelta)
    changes: list[SourceFileChange] = Field(min_length=1, max_length=20)

    @field_validator("changes")
    @classmethod
    def change_paths_are_unique(
        cls, value: list[SourceFileChange]
    ) -> list[SourceFileChange]:
        paths = [item.path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("SourceFileChangeSet paths must be unique")
        return value


class SourceChangeApplyReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["passed"] = "passed"
    source_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    materialized_files: list[str] = Field(min_length=1, max_length=20)
    candidate_source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: list[str] = Field(min_length=1, max_length=20)


# Read-only compatibility for Artifact payloads created before
# SourceFileChangeSet replaced model-generated unified diffs.
class SourcePatchOperation(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    operation: Literal["modify", "add", "delete"]
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    unified_diff: str = Field(min_length=1, max_length=120_000)

    @field_validator("path")
    @classmethod
    def path_is_normalized_relative_posix(cls, value: str) -> str:
        normalized = value.strip()
        parts = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or "\\" in normalized
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("Patch path must be a normalized relative POSIX path")
        return normalized

    @model_validator(mode="after")
    def hash_matches_operation(self) -> SourcePatchOperation:
        if self.operation in {"modify", "delete"} and self.before_hash is None:
            raise ValueError("modify/delete patches require before_hash")
        if self.operation == "add" and self.before_hash is not None:
            raise ValueError("add patches cannot include before_hash")
        return self


class SourcePatchSet(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    base_version_id: str = Field(min_length=1, max_length=80)
    base_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=1, max_length=800)
    app_spec_delta: AppSpecDelta = Field(default_factory=AppSpecDelta)
    patches: list[SourcePatchOperation] = Field(min_length=1, max_length=20)

    @field_validator("patches")
    @classmethod
    def patch_paths_are_unique(
        cls, value: list[SourcePatchOperation]
    ) -> list[SourcePatchOperation]:
        paths = [item.path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("SourcePatchSet paths must be unique")
        return value


class SourcePatchApplyReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["passed"] = "passed"
    source_context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_files: list[str] = Field(min_length=1, max_length=20)
    candidate_source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: list[str] = Field(min_length=1, max_length=20)


class SourceDiff(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    base_version_id: str
    changed_files: list[str] = Field(default_factory=list, max_length=20)
    added_files: list[str] = Field(default_factory=list, max_length=20)
    removed_files: list[str] = Field(default_factory=list, max_length=20)
    line_additions: int = Field(ge=0)
    line_deletions: int = Field(ge=0)
    unified_diff: str = Field(default="", max_length=120_000)


class ValidationCheck(BaseModel):
    check_id: str
    label: str
    status: Literal["pass", "fail", "warning"]
    root_cause: Literal["app_spec", "renderer", "platform", "unknown"] = "unknown"
    resolvable: bool = False
    detail: str | None = None


class ValidationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    passed: bool
    checks: list[ValidationCheck]


class ExecutionRequest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_id: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=1, max_length=80)
    attempt: int = Field(ge=1)
    adapter_id: Literal["web-static-v1"] = "web-static-v1"
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    product_spec_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    architecture_design_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt: str = Field(min_length=1, max_length=4000)
    blueprint: Blueprint
    architecture_design: ArchitectureDesign
    app_spec: AppSpec
    source_bundle: SourceBundle
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=30)
    deadline_ms: int = Field(ge=1_000, le=600_000)


class ExecutionEvent(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_id: str
    sequence: int = Field(ge=1)
    type: Literal[
        "execution.accepted",
        "source.materializing",
        "source.materialized",
        "build.started",
        "build.completed",
        "test.started",
        "test.completed",
        "validation.started",
        "validation.completed",
        "execution.completed",
        "execution.failed",
        "execution.cancelled",
    ]
    timestamp: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandExecution(BaseModel):
    status: Literal["passed", "failed", "cancelled", "timeout", "not_run"]
    exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    stdout: str = Field(default="", max_length=20_000)
    stderr: str = Field(default="", max_length=20_000)


class ExecutionReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_id: str
    adapter_id: str
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed", "failed", "cancelled"]
    build: CommandExecution
    test: CommandExecution
    tests_collected: int = Field(ge=0)
    tests_passed: int = Field(ge=0)
    tests_failed: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=1000)


class BuildArtifactFile(BaseModel):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=120_000)
    size_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class BuildArtifact(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    files: list[BuildArtifactFile] = Field(default_factory=list, max_length=20)
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExecutionResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    execution_id: str
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_id: str
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["passed", "failed", "cancelled"]
    build_artifact: BuildArtifact | None = None
    execution_report: ExecutionReport
    validation_report: ValidationReport


class DataCheck(BaseModel):
    check_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    status: Literal["pass", "warning", "not_applicable"]
    detail: str = Field(min_length=1, max_length=400)


class DataProfile(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: str = Field(min_length=1, max_length=500)
    sources: list[str] = Field(default_factory=list, max_length=12)
    entities: list[str] = Field(default_factory=list, max_length=20)
    checks: list[DataCheck] = Field(default_factory=list, max_length=20)
    insights: list[str] = Field(default_factory=list, max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    analyst_mode: Literal["agent_analysis", "deterministic_only"] = "agent_analysis"


class ReviewIssue(BaseModel):
    severity: Literal["blocker", "warning", "info"]
    root_cause: Literal[
        "requirements", "architecture", "data", "implementation", "platform", "unknown"
    ] = "unknown"
    summary: str = Field(min_length=1, max_length=300)
    evidence_refs: list[str] = Field(default_factory=list, max_length=12)


class ReviewReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: str = Field(min_length=1, max_length=500)
    verdict: Literal["accept", "rework", "needs_input"] = "accept"
    requirement_checks: list[str] = Field(default_factory=list, max_length=20)
    engineering_checks: list[str] = Field(default_factory=list, max_length=20)
    data_findings: list[str] = Field(default_factory=list, max_length=20)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    suggested_actions: list[Literal["edit", "resolve", "retry", "accept"]]
    reviewer_mode: Literal["agent_review", "deterministic_only"] = "agent_review"


class RunCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: Mode = Mode.TEAM
    model: str | None = Field(default=None, min_length=1, max_length=100)
    attachments: list[AttachmentMeta] = Field(default_factory=list, max_length=5)

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt cannot be blank")
        return value


class BlueprintApproval(BaseModel):
    blueprint: Blueprint


class RewriteConfirmation(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Confirmed alternative cannot be blank")
        return value


class RevisionRequest(BaseModel):
    hero_title: str | None = Field(default=None, min_length=1, max_length=120)
    hero_body: str | None = Field(default=None, min_length=1, max_length=300)
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("hero_title", "hero_body", "primary_color")
    @classmethod
    def at_least_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Revision values cannot be blank")
        return value


class PublishRequest(BaseModel):
    version_id: str
    strategy: PublicationStrategy = PublicationStrategy.SPECIFY_VERSION


class HumanTaskView(BaseModel):
    id: str
    project_id: str
    run_id: str
    kind: HumanTaskKind
    status: HumanTaskStatus
    stage: str
    prompt: str
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class RunView(BaseModel):
    run_id: str
    project_id: str
    session_id: str
    prompt: str
    mode: Mode
    model: str
    trigger: Literal["build", "ai_edit"] = "build"
    base_version_id: str | None = None
    status: RunStatus
    current_stage: str
    blueprint: Blueprint | None = None
    product_spec: ProductSpec | None = None
    architecture_design: ArchitectureDesign | None = None
    architecture_spec: ArchitectureSpec | None = None
    app_spec: AppSpec | None = None
    source_bundle: SourceBundle | None = None
    execution_report: ExecutionReport | None = None
    data_profile: DataProfile | None = None
    validation_report: ValidationReport | None = None
    review_report: ReviewReport | None = None
    build_job_id: str | None = None
    version_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    pending_human_task: HumanTaskView | None = None
    created_at: datetime
    updated_at: datetime


class HumanTaskResponse(BaseModel):
    response: str | None = Field(default=None, max_length=4000)
    decision: Literal["approve", "reject", "cancel"] | None = None

    @field_validator("response")
    @classmethod
    def response_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Human task response cannot be blank")
        return value.strip() if value else None


class ProjectFileEntry(BaseModel):
    path: str
    source: Literal["repository", "artifact"]
    size: int = Field(ge=0)
    kind: Literal["markdown", "json", "code", "text"] = "text"
    text: bool = True
    editable: bool = False
    render_mode: Literal["markdown", "source"] = "source"


class ProjectFileContent(BaseModel):
    path: str
    source: Literal["repository", "artifact"]
    content: str
    content_hash: str
    editable: bool = False
    kind: Literal["markdown", "json", "code", "text"] = "text"
    render_mode: Literal["markdown", "source"] = "source"


class ProjectFileSaveRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str
    expected_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    operation_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")


class ProjectFileSaveResult(BaseModel):
    path: str
    content_hash: str
    size: int = Field(ge=0)
    git_commit: str
    version: VersionView | None = None
    saved_at: datetime


class EventView(BaseModel):
    event_id: str
    sequence: int
    run_id: str
    type: str
    payload: dict[str, Any]
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class VersionView(BaseModel):
    id: str
    project_id: str
    run_id: str
    number: int
    source: VersionSource
    summary: str
    app_spec: AppSpec
    created_at: datetime
    git_commit: str | None = None


class DeploymentView(BaseModel):
    public_id: str
    project_id: str
    version_id: str
    strategy: PublicationStrategy
    status: Literal["live", "paused"]
    public_url: str


class ProjectView(BaseModel):
    id: str
    name: str
    status: ProjectStatus
    support_level: SupportLevel | None = None
    current_version_id: str | None = None
    deployment: DeploymentView | None = None
    created_at: datetime
    updated_at: datetime
    repository_ready: bool = False
    repository_branch: str = "main"


class ProjectMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    selected_files: list[str] = Field(default_factory=list, max_length=20)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("message")
    @classmethod
    def project_message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class ProjectMessageView(BaseModel):
    id: str
    project_id: str
    run_id: str | None = None
    role: Literal[
        "user",
        "lead",
        "product_manager",
        "architect",
        "engineer",
        "system",
    ]
    message_type: Literal[
        "request",
        "answer",
        "clarification",
        "clarification_response",
        "change_proposal",
        "change_brief",
        "agent_update",
        "result",
        "error",
    ]
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ProjectLeadDecision(BaseModel):
    intent: ProjectLeadIntent
    response: str = Field(min_length=1, max_length=1200)
    reason: str = Field(min_length=1, max_length=300)
    change_summary: str | None = Field(default=None, max_length=600)

    @field_validator("change_summary")
    @classmethod
    def change_summary_matches_intent(cls, value: str | None, info: Any) -> str | None:
        intent = info.data.get("intent")
        if intent == ProjectLeadIntent.PROPOSE_CHANGE and not (value and value.strip()):
            raise ValueError("A proposed change requires a change summary")
        return value.strip() if value else None


class ProjectMessageResult(BaseModel):
    intent: ProjectLeadIntent
    user_message: ProjectMessageView
    lead_message: ProjectMessageView
    proposal_id: str | None = None
    model: str
    fallback_provider: str | None = None


class QuotaView(BaseModel):
    limit: int
    used: int
    reserved: int
    remaining: int


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    llm_provider: str
    database: str


class ModelOption(BaseModel):
    id: str
    label: str
    usage: Literal["medium", "extra_high", "local"]


class ModelsView(BaseModel):
    provider: str
    fallback_provider: str | None = None
    sandbox_available: bool = False
    default_model: str
    models: list[ModelOption]


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=10, max_length=200)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class UserView(BaseModel):
    id: str
    username: str
    display_name: str
    role: Literal["user", "admin"]


class AdminUserView(UserView):
    role: Literal["admin"] = "admin"


class AdminUserRoleUpdate(BaseModel):
    role: Literal["admin"]


class AdminUserSummary(BaseModel):
    id: str
    username: str
    display_name: str
    plan: str
    quota_limit: int
    quota_used: int
    quota_reserved: int
    project_count: int
    created_at: datetime


class AdminUserList(BaseModel):
    items: list[AdminUserSummary]
    page: int
    page_size: int
    total: int


class AdminRunSummary(BaseModel):
    id: str
    model: str
    status: str
    current_stage: str
    error_code: str | None = None
    error_summary: str | None = None
    quota_spent: int
    created_at: datetime
    updated_at: datetime


class AdminProjectSummary(BaseModel):
    id: str
    name: str
    summary: str
    status: str
    updated_at: datetime
    support_level: str | None = None
    latest_run: AdminRunSummary | None = None


class AdminProjectList(BaseModel):
    items: list[AdminProjectSummary]
    page: int
    page_size: int
    total: int


class AdminProjectDetail(BaseModel):
    project: AdminProjectSummary
    prompt_summary: str
    events: list[EventView] = Field(default_factory=list)


class LeadMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    force_team: bool = False
    model: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        return value


class LeadClarificationOption(BaseModel):
    value: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=240)

    @field_validator("value", "label", "description")
    @classmethod
    def clarification_option_text_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Clarification option text cannot be blank")
        return value


class LeadClarificationQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=240)
    options: list[LeadClarificationOption] = Field(min_length=2, max_length=6)

    @field_validator("id", "question")
    @classmethod
    def clarification_question_text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Clarification question text cannot be blank")
        return value

    @model_validator(mode="after")
    def option_values_are_unique(self) -> LeadClarificationQuestion:
        values = [option.value for option in self.options]
        if len(values) != len(set(values)):
            raise ValueError("Clarification option values must be unique")
        return self


class LeadDecision(BaseModel):
    route: LeadRoute
    response: str = Field(min_length=1, max_length=800)
    reason: str = Field(min_length=1, max_length=300)
    clarification_questions: list[LeadClarificationQuestion] = Field(
        default_factory=list,
        max_length=4,
    )

    @model_validator(mode="after")
    def clarification_questions_match_route(self) -> LeadDecision:
        if self.route == LeadRoute.CLARIFY and not self.clarification_questions:
            raise ValueError("A clarify route requires structured clarification questions")
        if self.route != LeadRoute.CLARIFY and self.clarification_questions:
            raise ValueError("Only a clarify route can include clarification questions")
        question_ids = [question.id for question in self.clarification_questions]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Clarification question ids must be unique")
        return self


class LeadDecisionView(LeadDecision):
    message_id: str
    model: str
    fallback_provider: str | None = None


class SandboxSessionView(BaseModel):
    session_id: str
    project_id: str
    websocket_path: str
    expires_at: datetime


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
