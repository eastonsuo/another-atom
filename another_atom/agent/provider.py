import re
from typing import Protocol

from another_atom.contracts.schemas import (
    AppSpec,
    Blueprint,
    Mode,
    PageSpec,
    ProductItem,
    QAReview,
    SupportLevel,
    ValidationReport,
    VisualSpec,
)


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str

    def create_blueprint(self, prompt: str, mode: Mode) -> Blueprint: ...

    def create_visual_spec(self, blueprint: Blueprint) -> VisualSpec: ...

    def create_app_spec(
        self, blueprint: Blueprint, visual_spec: VisualSpec, prompt: str
    ) -> AppSpec: ...

    def review(
        self, app_spec: AppSpec, validation_report: ValidationReport, prompt: str
    ) -> QAReview: ...


class MockLLMProvider:
    """Deterministic contract-compatible provider used by local development and tests."""

    name = "mock"

    _unsupported_terms = {
        "crm",
        "erp",
        "社交网络",
        "即时通讯",
        "工作流平台",
        "数据分析后台",
    }
    _adapted_terms = {
        "支付",
        "订单",
        "登录",
        "注册",
        "数据库",
        "stripe",
        "login",
        "payment",
        "购物车结算",
    }

    def create_blueprint(self, prompt: str, mode: Mode) -> Blueprint:
        self._raise_if_requested(prompt, "llm")
        normalized = prompt.lower()
        if any(term in normalized for term in self._unsupported_terms):
            support_level = SupportLevel.UNSUPPORTED
        elif any(term in normalized for term in self._adapted_terms):
            support_level = SupportLevel.ADAPTED
        else:
            support_level = SupportLevel.SUPPORTED

        project_name = self._project_name(prompt)
        omitted = (
            ["V1 does not implement authentication, payment, or transactional backends"]
            if support_level == SupportLevel.ADAPTED
            else []
        )
        return Blueprint(
            project_name=project_name,
            support_level=support_level,
            support_reasons=[self._support_reason(support_level)],
            mapped_requirements=[
                "Responsive product catalog",
                "Product detail navigation",
                "Editable visual direction",
            ],
            omitted_requirements=omitted,
            rewrite_suggestion=(
                "Describe a product showcase or catalog with Home, Catalog, and Product pages."
                if support_level == SupportLevel.UNSUPPORTED
                else None
            ),
            pages=["Home", "Catalog", "Product"],
            modules=["Hero", "Featured products", "Catalog grid", "Product detail"],
            visual_direction="Editorial commerce with crisp typography and restrained color",
            data_requirements=["Controlled sample product data"],
        )

    def create_visual_spec(self, blueprint: Blueprint) -> VisualSpec:
        return VisualSpec(
            primary_color="#151515",
            accent_color="#E85D3F",
            background_color="#F5F2EA",
            typography="sans",
            density="comfortable",
            style=f"{blueprint.visual_direction}; high-contrast editorial product photography",
        )

    def create_app_spec(
        self, blueprint: Blueprint, visual_spec: VisualSpec, prompt: str
    ) -> AppSpec:
        self._raise_if_requested(prompt, "engineer")
        return AppSpec(
            project_name=blueprint.project_name,
            tagline="Objects selected for everyday clarity",
            hero_title=f"Meet {blueprint.project_name}",
            hero_body=(
                "A focused catalog of useful objects, presented with enough detail to choose "
                "with confidence."
            ),
            primary_color=visual_spec.primary_color,
            accent_color=visual_spec.accent_color,
            background_color=visual_spec.background_color,
            pages=[
                PageSpec(route="/", name="Home", sections=["hero", "featured", "principles"]),
                PageSpec(route="/catalog", name="Catalog", sections=["filters", "product-grid"]),
                PageSpec(
                    route="/product/orbit-lamp",
                    name="Product",
                    sections=["gallery", "details", "related"],
                ),
            ],
            products=self._products(),
        )

    def review(
        self, app_spec: AppSpec, validation_report: ValidationReport, prompt: str
    ) -> QAReview:
        self._raise_if_requested(prompt, "qa-provider")
        forced_warning = "[fail:qa]" in prompt.lower()
        warnings = [
            check.detail or check.label
            for check in validation_report.checks
            if check.status != "pass"
        ]
        if forced_warning:
            warnings.append("Mock QA requested a degraded completion for acceptance testing")
        return QAReview(
            summary=(
                f"Reviewed {app_spec.project_name}: deterministic checks "
                f"{'passed' if validation_report.passed else 'found blocking issues'}."
            ),
            mandatory_checks=[check.label for check in validation_report.checks],
            warnings=warnings,
            suggested_actions=["edit"] if warnings else ["accept"],
        )

    @staticmethod
    def _raise_if_requested(prompt: str, stage: str) -> None:
        lowered = prompt.lower()
        if "[fail:llm]" in lowered or f"[fail:{stage}]" in lowered:
            raise LLMProviderError(f"Mock LLM failure requested for {stage}")

    @staticmethod
    def _project_name(prompt: str) -> str:
        compact = " ".join(prompt.replace("\n", " ").split())
        english_match = re.search(
            r"(?:called|named)\s+([a-z0-9][a-z0-9 &'\-]{0,60}?)"
            r"(?=\s+(?:for|with|that|using)\b|[,.，。]|$)",
            compact,
            flags=re.IGNORECASE,
        )
        if english_match:
            return english_match.group(1).strip().title()[:80]
        chinese_match = re.search(r"(?:叫做|名为)\s*([^，。,.]{1,40})", compact)
        if chinese_match:
            return chinese_match.group(1).strip()[:80]
        return "Mono Market"

    @staticmethod
    def _support_reason(level: SupportLevel) -> str:
        return {
            SupportLevel.SUPPORTED: "The request maps to the controlled catalog renderer.",
            SupportLevel.ADAPTED: (
                "The catalog can be built after excluding transactional features."
            ),
            SupportLevel.UNSUPPORTED: "The primary workflow is outside the V1 catalog boundary.",
        }[level]

    @staticmethod
    def _products() -> list[ProductItem]:
        return [
            ProductItem(
                id="orbit-lamp",
                name="Orbit Lamp",
                category="Lighting",
                price="$128",
                description="A compact aluminum desk lamp with warm, directional light.",
                image_url="https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=1200&q=80",
            ),
            ProductItem(
                id="fold-chair",
                name="Fold Chair",
                category="Furniture",
                price="$210",
                description="A slim oak chair designed for flexible rooms and daily use.",
                image_url="https://images.unsplash.com/photo-1503602642458-232111445657?auto=format&fit=crop&w=1200&q=80",
            ),
            ProductItem(
                id="field-clock",
                name="Field Clock",
                category="Objects",
                price="$74",
                description="A quiet table clock with a legible face and tactile controls.",
                image_url="https://images.unsplash.com/photo-1563861826100-9cb868fdbe1c?auto=format&fit=crop&w=1200&q=80",
            ),
            ProductItem(
                id="arc-vessel",
                name="Arc Vessel",
                category="Home",
                price="$56",
                description="A hand-finished ceramic vessel for stems or open shelving.",
                image_url="https://images.unsplash.com/photo-1610701596007-11502861dcfa?auto=format&fit=crop&w=1200&q=80",
            ),
        ]


def get_llm_provider() -> LLMProvider:
    return MockLLMProvider()
