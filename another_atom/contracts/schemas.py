from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Mode(StrEnum):
    ENGINEER = "engineer"
    TEAM = "team"


class SupportLevel(StrEnum):
    SUPPORTED = "supported"
    ADAPTED = "adapted"
    UNSUPPORTED = "unsupported"


class RunStatus(StrEnum):
    PRODUCT_RUNNING = "product_running"
    AWAITING_APPROVAL = "awaiting_approval"
    DESIGNER_RUNNING = "designer_running"
    ENGINEER_RUNNING = "engineer_running"
    BUILD_QUEUED = "build_queued"
    BUILDING = "building"
    QA_RUNNING = "qa_running"
    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildStatus(StrEnum):
    QUEUED = "queued"
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
    BLUEPRINT = "blueprint"
    VISUAL_SPEC = "visual_spec"
    APP_SPEC = "app_spec"
    VALIDATION_REPORT = "validation_report"
    QA_REVIEW = "qa_review"


class VersionSource(StrEnum):
    BUILD = "build"
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
    product_type: Literal["product_catalog"] = "product_catalog"
    support_level: SupportLevel
    support_reasons: list[str] = Field(default_factory=list, max_length=8)
    mapped_requirements: list[str] = Field(default_factory=list, max_length=12)
    omitted_requirements: list[str] = Field(default_factory=list, max_length=12)
    rewrite_suggestion: str | None = Field(default=None, max_length=500)
    capability_policy_version: Literal["catalog-v1"] = "catalog-v1"
    pages: list[str] = Field(min_length=1, max_length=5)
    modules: list[str] = Field(min_length=1, max_length=12)
    visual_direction: str = Field(min_length=1, max_length=240)
    data_requirements: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("pages")
    @classmethod
    def pages_are_supported(cls, value: list[str]) -> list[str]:
        allowed = {"Home", "Catalog", "Product"}
        if not set(value).issubset(allowed):
            raise ValueError("V1 pages must stay within Home, Catalog, and Product")
        return value


class VisualSpec(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
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
    route: str = Field(pattern=r"^/(?:catalog|product/[a-z0-9-]+)?$")
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
    pages: list[PageSpec] = Field(min_length=3, max_length=6)
    products: list[ProductItem] = Field(min_length=3, max_length=12)


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


class QAReview(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    summary: str
    mandatory_checks: list[str]
    warnings: list[str] = Field(default_factory=list)
    suggested_actions: list[Literal["edit", "resolve", "retry", "accept"]]
    qa_mode: Literal["agent_review", "deterministic_only"] = "agent_review"


class RunCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    mode: Mode = Mode.TEAM
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


class RunView(BaseModel):
    run_id: str
    project_id: str
    session_id: str
    mode: Mode
    status: RunStatus
    current_stage: str
    blueprint: Blueprint | None = None
    visual_spec: VisualSpec | None = None
    app_spec: AppSpec | None = None
    validation_report: ValidationReport | None = None
    qa_review: QAReview | None = None
    build_job_id: str | None = None
    version_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


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


class QuotaView(BaseModel):
    limit: int
    used: int
    reserved: int
    remaining: int


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    llm_provider: str
    database: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
