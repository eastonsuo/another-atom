import re
from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    Blueprint,
    DataReview,
    Mode,
    PageSpec,
    ProductItem,
    SupportLevel,
    ValidationReport,
)

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderUsage:
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    name: str
    reservation_units: int

    def take_usage(self) -> ProviderUsage: ...

    def create_blueprint(self, prompt: str, mode: Mode) -> Blueprint: ...

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec: ...

    def create_app_spec(
        self, blueprint: Blueprint, architecture_spec: ArchitectureSpec, prompt: str
    ) -> AppSpec: ...

    def analyze(
        self, app_spec: AppSpec, validation_report: ValidationReport, prompt: str
    ) -> DataReview: ...


class MockLLMProvider:
    """Deterministic contract-compatible provider used by local development and tests."""

    name = "mock"
    reservation_units = 1

    def __init__(self) -> None:
        self._usage = ProviderUsage()

    def take_usage(self) -> ProviderUsage:
        usage = self._usage
        self._usage = ProviderUsage()
        return usage

    def _record_request(self) -> None:
        self._usage = ProviderUsage(request_count=self._usage.request_count + 1)

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
        self._record_request()
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

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec:
        self._record_request()
        return ArchitectureSpec(
            architecture_summary=(
                "A three-route catalog rendered from a validated AppSpec with no generated backend."
            ),
            page_strategy=["Home discovery", "Catalog browsing", "Product inspection"],
            data_entities=["Product", "Category"],
            primary_color="#151515",
            accent_color="#E85D3F",
            background_color="#F5F2EA",
            typography="sans",
            density="comfortable",
            style=f"{blueprint.visual_direction}; high-contrast editorial product photography",
        )

    def create_app_spec(
        self, blueprint: Blueprint, architecture_spec: ArchitectureSpec, prompt: str
    ) -> AppSpec:
        self._record_request()
        self._raise_if_requested(prompt, "engineer")
        return AppSpec(
            project_name=blueprint.project_name,
            tagline="Objects selected for everyday clarity",
            hero_title=f"Meet {blueprint.project_name}",
            hero_body=(
                "A focused catalog of useful objects, presented with enough detail to choose "
                "with confidence."
            ),
            primary_color=architecture_spec.primary_color,
            accent_color=architecture_spec.accent_color,
            background_color=architecture_spec.background_color,
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

    def analyze(
        self, app_spec: AppSpec, validation_report: ValidationReport, prompt: str
    ) -> DataReview:
        self._record_request()
        self._raise_if_requested(prompt, "data-provider")
        forced_warning = "[fail:data]" in prompt.lower()
        warnings = [
            check.detail or check.label
            for check in validation_report.checks
            if check.status != "pass"
        ]
        if forced_warning:
            warnings.append(
                "Mock Data review requested a degraded completion for acceptance testing"
            )
        return DataReview(
            summary=(
                f"Analyzed {app_spec.project_name}: deterministic checks "
                f"{'passed' if validation_report.passed else 'found blocking issues'}."
            ),
            data_checks=["Product identifiers are unique", "Catalog data is complete"],
            engineering_checks=[check.label for check in validation_report.checks],
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


class OllamaCloudProvider:
    name = "ollama"
    reservation_units = 2

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.ollama_api_key:
            raise LLMProviderError("OLLAMA_API_KEY is required for the Ollama provider")
        self.model = model or settings.ollama_model
        self.host = settings.ollama_host.rstrip("/")
        self.api_key = settings.ollama_api_key
        self.timeout = settings.ollama_timeout_seconds
        self._usage = ProviderUsage()

    def take_usage(self) -> ProviderUsage:
        usage = self._usage
        self._usage = ProviderUsage()
        return usage

    def _record_response_usage(self, body: dict) -> None:
        self._usage = ProviderUsage(
            request_count=self._usage.request_count,
            input_tokens=self._usage.input_tokens + int(body.get("prompt_eval_count", 0)),
            output_tokens=self._usage.output_tokens + int(body.get("eval_count", 0)),
        )

    def create_blueprint(self, prompt: str, mode: Mode) -> Blueprint:
        return self._structured_chat(
            Blueprint,
            "Product Manager",
            (
                "Turn the user request into the V1 Blueprint. V1 only supports product catalog "
                "sites with Home, Catalog, and Product pages. Classify support_level honestly as "
                "supported, adapted, or unsupported. Do not invent backend, auth, or payment "
                "support."
            ),
            {"request": prompt, "mode": mode.value},
        )

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec:
        return self._structured_chat(
            ArchitectureSpec,
            "Architect",
            (
                "Define a controlled three-route React catalog architecture and visual tokens. "
                "Use only Product and Category data entities and no generated backend."
            ),
            {"blueprint": blueprint.model_dump(mode="json")},
        )

    def create_app_spec(
        self, blueprint: Blueprint, architecture_spec: ArchitectureSpec, prompt: str
    ) -> AppSpec:
        return self._structured_chat(
            AppSpec,
            "Engineer",
            (
                "Produce an AppSpec for the fixed renderer. Include exactly the Home, Catalog, and "
                "at least one /product/<id> route plus 3-6 complete sample products. Use valid hex "
                "colors and stable lowercase product ids. Do not output source code or shell "
                "commands."
            ),
            {
                "request": prompt,
                "blueprint": blueprint.model_dump(mode="json"),
                "architecture_spec": architecture_spec.model_dump(mode="json"),
            },
        )

    def analyze(
        self, app_spec: AppSpec, validation_report: ValidationReport, prompt: str
    ) -> DataReview:
        return self._structured_chat(
            DataReview,
            "Data Analyst",
            (
                "Analyze catalog data completeness and summarize the immutable engineering "
                "validation. You cannot change failed checks to pass. Separate data_checks from "
                "engineering_checks."
            ),
            {
                "request": prompt,
                "app_spec": app_spec.model_dump(mode="json"),
                "validation_report": validation_report.model_dump(mode="json"),
            },
        )

    def _structured_chat(
        self,
        contract: type[T],
        role: str,
        instruction: str,
        payload: dict,
    ) -> T:
        schema = contract.model_json_schema()
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are the {role} in Another Atom. {instruction} "
                    "Return one JSON object only: no markdown fences, commentary, or hidden "
                    "reasoning. "
                    f"The JSON must satisfy this schema: {schema}"
                ),
            },
            {"role": "user", "content": str(payload)},
        ]
        try:
            for attempt in range(2):
                self._usage = ProviderUsage(
                    request_count=self._usage.request_count + 1,
                    input_tokens=self._usage.input_tokens,
                    output_tokens=self._usage.output_tokens,
                )
                response = httpx.post(
                    f"{self.host}/api/chat",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "messages": messages, "stream": False},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
                self._record_response_usage(body)
                content = body["message"]["content"]
                json_content = self._extract_json(content)
                try:
                    return contract.model_validate_json(json_content)
                except ValidationError as exc:
                    if attempt == 1:
                        raise
                    messages.extend(
                        [
                            {"role": "assistant", "content": json_content},
                            {
                                "role": "user",
                                "content": (
                                    "Correct the JSON to satisfy the schema. Return JSON only. "
                                    f"Validation errors: {exc.errors(include_input=False)}"
                                ),
                            },
                        ]
                    )
            raise ValueError("structured response repair did not complete")
        except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
            raise LLMProviderError(f"Ollama {role} output failed: {exc}") from exc

    @staticmethod
    def _extract_json(content: str) -> str:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("response did not contain a JSON object")
        return content[start : end + 1]


def get_llm_provider(model: str | None = None) -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return OllamaCloudProvider(model=model)
    return MockLLMProvider()
