import json
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
    LeadDecision,
    LeadRoute,
    Mode,
    PageSpec,
    ProductItem,
    SupportLevel,
    ValidationReport,
)

T = TypeVar("T", bound=BaseModel)

_BUILD_TERMS = (
    "build",
    "create",
    "make",
    "generate",
    "develop",
    "构建",
    "创建",
    "生成",
    "开发",
    "制作",
    "做一个",
    "给我一个",
    "帮我做",
)
_INQUIRY_PREFIXES = (
    "what can",
    "what does",
    "how does",
    "how can",
    "why ",
    "which ",
    "能做什么",
    "支持什么",
    "为什么",
    "如何",
    "怎么",
)


def _is_explicit_build_request(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    return not normalized.startswith(_INQUIRY_PREFIXES) and any(
        term in normalized for term in _BUILD_TERMS
    )


class LLMProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderUsage:
    request_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    fallback_provider: str | None = None


class LLMProvider(Protocol):
    name: str
    reservation_units: int

    def take_usage(self) -> ProviderUsage: ...

    def route_message(self, message: str, force_team: bool = False) -> LeadDecision: ...

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
        "minesweeper",
        "扫雷",
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

    def route_message(self, message: str, force_team: bool = False) -> LeadDecision:
        if force_team:
            return LeadDecision(
                route=LeadRoute.TEAM,
                response="I’ll send this request through the fixed product team.",
                reason="The user explicitly selected Call team.",
            )
        self._record_request()
        self._raise_if_requested(message, "lead")
        if _is_explicit_build_request(message):
            return LeadDecision(
                route=LeadRoute.TEAM,
                response="I’ll send this request through the fixed product team.",
                reason="The message explicitly requests a product build.",
            )
        return LeadDecision(
            route=LeadRoute.DIRECT,
            response=(
                "V1 can build controlled product catalogs with Home, Catalog, and Product pages. "
                "Tell me the catalog, products, and visual direction when you want the team "
                "to build."
            ),
            reason="The message is a question or clarification rather than a build instruction.",
        )

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
            rewrite_suggestion=(self._catalog_rewrite(prompt) if support_level == SupportLevel.UNSUPPORTED else None),
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
        if "[fail:platform]" in lowered:
            raise RuntimeError(f"Mock platform failure requested for {stage}")
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
    def _catalog_rewrite(prompt: str) -> str:
        """Create a deterministic, buildable PM draft that preserves the user's theme."""
        normalized = prompt.lower()
        if "crm" in normalized:
            return (
                "Build a sales productivity product catalog featuring customer-management "
                "templates, sales dashboards, and team toolkits, with Home, Catalog, and "
                "Product pages and a clear professional visual style."
            )
        if "erp" in normalized:
            return (
                "Build a business operations toolkit catalog featuring inventory templates, "
                "planning packs, and finance worksheets, with Home, Catalog, and Product pages."
            )
        if "minesweeper" in normalized or "扫雷" in normalized:
            return (
                "创建一个扫雷主题商品目录，展示桌游、收藏品和周边商品，包含首页、目录页和"
                "商品详情页，采用复古像素风格和清晰的商品分类。"
            )
        if "社交网络" in normalized:
            theme = "创作者社区周边商品"
        elif "即时通讯" in normalized:
            theme = "沟通主题办公工具"
        elif "工作流平台" in normalized:
            theme = "效率模板与自动化工具"
        elif "数据分析后台" in normalized:
            theme = "数据分析模板与工具"
        else:
            theme = "与原始创意相关的商品"
        return f"创建一个{theme}目录，包含首页、目录页和商品详情页，并为商品分类、视觉风格和详情展示补充完整内容。"

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
        self.lead_timeout = settings.ollama_lead_timeout_seconds
        self.failover_timeout = settings.ollama_failover_timeout_seconds
        self.deepseek_api_key = settings.deepseek_api_key
        self.deepseek_host = settings.deepseek_host.rstrip("/")
        self.reservation_units = 3 if self.deepseek_api_key else 2
        self._usage = ProviderUsage()

    def take_usage(self) -> ProviderUsage:
        usage = self._usage
        self._usage = ProviderUsage()
        return usage

    def route_message(self, message: str, force_team: bool = False) -> LeadDecision:
        if force_team:
            return LeadDecision(
                route=LeadRoute.TEAM,
                response="I’ll send this request through the fixed product team.",
                reason="The user explicitly selected Call team.",
            )
        return self._structured_chat(
            LeadDecision,
            "Lead",
            (
                "Choose exactly one route. Use team only when the user explicitly asks to build, "
                "create, generate, revise, or restore a product. Use direct for questions, "
                "clarification, capability discussion, or ambiguous intent. Direct must not claim "
                "that files or a Project were created. Team invokes the complete fixed Product "
                "Manager, Architect, Engineer, and Data Analyst pipeline."
            ),
            {"message": message},
            timeout_seconds=self.lead_timeout,
            think=False,
        )

    def _record_response_usage(self, body: dict) -> None:
        self._usage = ProviderUsage(
            request_count=self._usage.request_count,
            input_tokens=self._usage.input_tokens + int(body.get("prompt_eval_count", 0)),
            output_tokens=self._usage.output_tokens + int(body.get("eval_count", 0)),
            fallback_provider=self._usage.fallback_provider,
        )

    def create_blueprint(self, prompt: str, mode: Mode) -> Blueprint:
        return self._structured_chat(
            Blueprint,
            "Product Manager",
            (
                "Turn the user request into the V1 Blueprint. V1 only supports product catalog "
                "sites with Home, Catalog, and Product pages. Classify support_level honestly as "
                "supported, adapted, or unsupported. Do not invent backend, auth, or payment "
                "support. mapped_requirements may only contain these canonical claims: "
                "Responsive product catalog, Product detail navigation, Editable visual direction. "
                "When the original workflow is unsupported, act as a proactive Product Manager: "
                "rewrite_suggestion must be a complete build instruction that preserves the "
                "request's recognizable theme while converting it into the supported catalog "
                "scope. Expand the catalog concept with concrete product categories, Home, "
                "Catalog, and Product pages, and a visual direction. Write it in the same language "
                "as the user. It must be ready for the user to confirm unchanged, not advice asking "
                "the user to describe or narrow the request."
            ),
            {"request": prompt, "mode": mode.value},
        )

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec:
        return self._structured_chat(
            ArchitectureSpec,
            "Architect",
            (
                "Define a controlled three-route React catalog architecture and visual tokens. "
                "Use only Product and Category data entities and no generated backend. Primary "
                "text against background must meet at least 4.5:1 contrast and accent against "
                "background at least 3:1. Preserve the requested visual theme while choosing "
                "accessible token values."
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
                "colors and stable lowercase product ids. Copy primary_color, accent_color, and "
                "background_color exactly from ArchitectureSpec. Do not output source code or "
                "shell commands."
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
        timeout_seconds: float | None = None,
        think: bool | None = None,
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
                    fallback_provider=self._usage.fallback_provider,
                )
                request_body = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    # Constrain the model to emit strictly valid JSON matching the
                    # contract. Reasoning-capable models (DeepSeek V4) otherwise emit
                    # think-text and prose that corrupt free-form JSON extraction.
                    "format": schema,
                }
                if think is not None:
                    request_body["think"] = think
                primary_timeout = timeout_seconds or self.timeout
                if self.deepseek_api_key:
                    primary_timeout = min(primary_timeout, self.failover_timeout)
                try:
                    response = httpx.post(
                        f"{self.host}/api/chat",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=request_body,
                        timeout=primary_timeout,
                    )
                except httpx.TimeoutException:
                    if not self.deepseek_api_key:
                        raise
                    self._usage = ProviderUsage(
                        request_count=self._usage.request_count,
                        input_tokens=self._usage.input_tokens,
                        output_tokens=self._usage.output_tokens,
                        fallback_provider="deepseek",
                    )
                    return self._deepseek_structured_chat(
                        contract,
                        role,
                        messages,
                        think=think,
                    )
                response.raise_for_status()
                body = response.json()
                self._record_response_usage(body)
                content = self._message_content(body)
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

    def _deepseek_structured_chat(
        self,
        contract: type[T],
        role: str,
        messages: list[dict[str, str]],
        *,
        think: bool | None,
    ) -> T:
        if not self.deepseek_api_key:
            raise LLMProviderError("DEEPSEEK_API_KEY is required for provider fallback")
        fallback_messages = [dict(message) for message in messages]
        try:
            for attempt in range(2):
                self._usage = ProviderUsage(
                    request_count=self._usage.request_count + 1,
                    input_tokens=self._usage.input_tokens,
                    output_tokens=self._usage.output_tokens,
                    fallback_provider="deepseek",
                )
                request_body: dict = {
                    "model": self.model,
                    "messages": fallback_messages,
                    "stream": False,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 4096,
                    "temperature": 0.2,
                }
                if think is not None:
                    request_body["thinking"] = {
                        "type": "enabled" if think else "disabled"
                    }
                response = httpx.post(
                    f"{self.deepseek_host}/chat/completions",
                    headers={"Authorization": f"Bearer {self.deepseek_api_key}"},
                    json=request_body,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.json()
                usage = body.get("usage") or {}
                self._usage = ProviderUsage(
                    request_count=self._usage.request_count,
                    input_tokens=self._usage.input_tokens + int(usage.get("prompt_tokens", 0)),
                    output_tokens=self._usage.output_tokens
                    + int(usage.get("completion_tokens", 0)),
                    fallback_provider="deepseek",
                )
                content = body["choices"][0]["message"]["content"]
                json_content = self._extract_json(content)
                try:
                    return contract.model_validate_json(json_content)
                except ValidationError as exc:
                    if attempt == 1:
                        raise
                    fallback_messages.extend(
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
            raise ValueError("DeepSeek structured response repair did not complete")
        except (httpx.HTTPError, KeyError, TypeError, ValidationError, ValueError) as exc:
            raise LLMProviderError(f"DeepSeek official {role} output failed: {exc}") from exc

    @staticmethod
    def _message_content(body: dict) -> str:
        message = body.get("message")
        if not isinstance(message, dict):
            raise ValueError("response did not contain a chat message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("response message content was empty")
        return content

    @staticmethod
    def _extract_json(content: str) -> str:
        """Return the first brace-balanced region that parses as valid JSON.

        Reasoning models frequently prepend hidden-thought text (which can itself
        contain decoy braces such as ``{x}``), wrap the answer in markdown fences,
        or append trailing prose. Naively slicing from the first ``{`` to the last
        ``}`` breaks on all of those. We instead scan each ``{``-anchored,
        brace-balanced region (respecting string literals and escapes) and return
        the first one that is actually valid JSON, skipping non-JSON decoys.
        """
        length = len(content)
        for start in range(length):
            if content[start] != "{":
                continue
            candidate = OllamaCloudProvider._balanced_object(content, start)
            if candidate is None:
                continue
            try:
                json.loads(candidate)
            except json.JSONDecodeError:
                continue
            return candidate
        raise ValueError("response did not contain a JSON object")

    @staticmethod
    def _balanced_object(content: str, start: int) -> str | None:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(content)):
            char = content[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return content[start : index + 1]
        return None


def get_llm_provider(model: str | None = None) -> LLMProvider:
    settings = get_settings()
    if settings.llm_provider == "ollama":
        return OllamaCloudProvider(model=model)
    return MockLLMProvider()
