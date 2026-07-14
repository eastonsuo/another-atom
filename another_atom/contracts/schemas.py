from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Mode(StrEnum):
    ENGINEER = "engineer"
    TEAM = "team"


class LeadRoute(StrEnum):
    DIRECT = "direct"
    TEAM = "team"


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
    BUILDING = "building"
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
    SOURCE_DIFF = "source_diff"
    BLUEPRINT = "blueprint"
    ARCHITECTURE_SPEC = "architecture_spec"
    APP_SPEC = "app_spec"
    APP_SPEC_REPAIR = "app_spec_repair"
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
    size: int = Field(ge=0, le=256_000)
    content: str = Field(max_length=256_000)


class BaseSourceSnapshot(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    base_version_id: str
    base_git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    files: list[SourceSnapshotFile] = Field(min_length=1, max_length=8)
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


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
    architecture_spec: ArchitectureSpec | None = None
    app_spec: AppSpec | None = None
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


class VersionView(BaseModel):
    id: str
    project_id: str
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
    role: Literal["user", "lead", "system"]
    message_type: Literal[
        "request",
        "answer",
        "clarification",
        "clarification_response",
        "change_brief",
        "result",
        "error",
    ]
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


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


class LeadDecision(BaseModel):
    route: LeadRoute
    response: str = Field(min_length=1, max_length=800)
    reason: str = Field(min_length=1, max_length=300)


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
