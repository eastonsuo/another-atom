import html as html_lib
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
    DataCheck,
    DataProfile,
    LeadDecision,
    LeadRoute,
    Mode,
    PageSpec,
    ProductItem,
    ReviewIssue,
    ReviewReport,
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

    def analyze_data(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        prompt: str,
    ) -> DataProfile: ...

    def review(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        data_profile: DataProfile,
        validation_report: ValidationReport,
        prompt: str,
    ) -> ReviewReport: ...


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
        "native ios",
        "native android",
        "原生 ios",
        "原生安卓",
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
        "crm",
        "erp",
        "社交网络",
        "即时通讯",
        "工作流平台",
        "数据分析后台",
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
                "Another Atom builds browser-based applications from natural-language requirements. "
                "Describe the product behavior, content, interactions, and visual direction when "
                "you want the team to build."
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
        is_game = any(term in normalized for term in ("minesweeper", "扫雷", "game", "游戏"))
        is_catalog = any(
            term in normalized
            for term in ("catalog", "storefront", "shop", "store", "商品目录", "商品站", "商店")
        )
        product_type = (
            "web_game" if is_game else "product_catalog" if is_catalog else "web_application"
        )
        omitted = (
            ["Server-side authentication, payment, and persistent backend writes are excluded"]
            if support_level == SupportLevel.ADAPTED
            else []
        )
        if is_game:
            mapped = [
                "Interactive browser game",
                "Client-side game state",
                "Responsive controls",
            ]
            pages = ["Game"]
            modules = ["Minefield", "Mine counter", "Timer", "Restart", "Win and loss states"]
            visual_direction = "Crisp retro game interface with readable grid states"
            data_requirements = ["Local board state", "Mine positions", "Elapsed time"]
        elif is_catalog:
            mapped = [
                "Responsive product catalog",
                "Product detail navigation",
                "Editable visual direction",
            ]
            pages = ["Home", "Catalog", "Product"]
            modules = ["Hero", "Featured products", "Catalog grid", "Product detail"]
            visual_direction = "Editorial commerce with crisp typography and restrained color"
            data_requirements = ["Controlled sample product data"]
        else:
            mapped = ["Browser-based interaction", "Responsive layout", "Local client-side state"]
            pages = ["Application"]
            modules = ["Primary workspace", "Controls", "Status feedback"]
            visual_direction = "Clear application interface with strong interaction feedback"
            data_requirements = ["Local application state"]
        return Blueprint(
            project_name=project_name,
            product_type=product_type,
            support_level=support_level,
            support_reasons=[self._support_reason(support_level)],
            mapped_requirements=mapped,
            omitted_requirements=omitted,
            rewrite_suggestion=(
                self._web_rewrite(prompt) if support_level == SupportLevel.UNSUPPORTED else None
            ),
            capability_policy_version="web-v1",
            pages=pages,
            modules=modules,
            visual_direction=visual_direction,
            data_requirements=data_requirements,
        )

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec:
        self._record_request()
        if blueprint.product_type == "web_game":
            return ArchitectureSpec(
                architecture_summary="A self-contained browser game with deterministic local state and no backend.",
                page_strategy=["Single game workspace", "Immediate state feedback"],
                data_entities=["Cell", "Board", "GameState"],
                primary_color="#17152B",
                accent_color="#D94F45",
                background_color="#FFF7DE",
                typography="sans",
                density="compact",
                style=blueprint.visual_direction,
            )
        if blueprint.product_type != "product_catalog":
            return ArchitectureSpec(
                architecture_summary="A self-contained responsive Web application using local browser state.",
                page_strategy=[f"{page} screen" for page in blueprint.pages],
                data_entities=["ApplicationState", "UserInput"],
                primary_color="#17152B",
                accent_color="#D94F45",
                background_color="#FFF7DE",
                typography="sans",
                density="comfortable",
                style=blueprint.visual_direction,
            )
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
        if blueprint.product_type == "web_game":
            html, css, javascript = self._minesweeper_code()
            return AppSpec(
                project_name=blueprint.project_name,
                tagline="Clear the field without triggering a mine",
                hero_title=blueprint.project_name,
                hero_body="Reveal safe cells, flag suspected mines, and clear the board.",
                primary_color=architecture_spec.primary_color,
                accent_color=architecture_spec.accent_color,
                background_color=architecture_spec.background_color,
                pages=[
                    PageSpec(route="/", name="Game", sections=["status", "minefield", "controls"])
                ],
                html=html,
                css=css,
                javascript=javascript,
            )
        if blueprint.product_type != "product_catalog":
            html, css, javascript = self._generic_app_code(blueprint, prompt)
            return AppSpec(
                project_name=blueprint.project_name,
                tagline="Interactive browser application",
                hero_title=blueprint.project_name,
                hero_body="A browser-based implementation of the requested workflow.",
                primary_color=architecture_spec.primary_color,
                accent_color=architecture_spec.accent_color,
                background_color=architecture_spec.background_color,
                pages=[
                    PageSpec(
                        route="/",
                        name=blueprint.pages[0],
                        sections=[
                            module.casefold().replace(" ", "-")[:40]
                            for module in blueprint.modules[:6]
                        ],
                    )
                ],
                html=html,
                css=css,
                javascript=javascript,
            )
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

    def analyze_data(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        prompt: str,
    ) -> DataProfile:
        self._record_request()
        self._raise_if_requested(prompt, "data-provider")
        forced_warning = "[fail:data]" in prompt.lower()
        warnings: list[str] = []
        if forced_warning:
            warnings.append("Mock Data Analyst warning requested for acceptance testing")
        if app_spec.products:
            identifiers = [item.id for item in app_spec.products]
            checks = [
                DataCheck(
                    check_id="unique-record-identifiers",
                    label="Product identifiers are unique",
                    status="pass" if len(identifiers) == len(set(identifiers)) else "warning",
                    detail="Checked product records emitted by AppSpec.",
                ),
                DataCheck(
                    check_id="catalog-record-completeness",
                    label="Catalog records contain the required display fields",
                    status="pass",
                    detail="Name, category, price, description, and image fields are populated.",
                ),
            ]
            sources = ["AppSpec.products"]
            entities = sorted({item.category for item in app_spec.products})
            insights = [
                f"{len(app_spec.products)} product records across {len(entities)} categories"
            ]
        else:
            checks = [
                DataCheck(
                    check_id="structured-dataset-not-required",
                    label="No standalone structured dataset is required",
                    status="not_applicable",
                    detail="The application uses local browser state rather than catalog records.",
                )
            ]
            sources = ["AppSpec local browser state"]
            entities = architecture_spec.data_entities
            insights = ["Application state remains local to the browser preview"]
        return DataProfile(
            summary=f"Analyzed the data model and local content for {blueprint.project_name}.",
            sources=sources,
            entities=entities,
            checks=checks,
            insights=insights,
            warnings=warnings,
        )

    def review(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        data_profile: DataProfile,
        validation_report: ValidationReport,
        prompt: str,
    ) -> ReviewReport:
        self._record_request()
        self._raise_if_requested(prompt, "reviewer-provider")
        forced_rework = "[review:rework]" in prompt.lower()
        failed_checks = [check for check in validation_report.checks if check.status == "fail"]
        issues = [
            ReviewIssue(
                severity="blocker",
                root_cause="implementation",
                summary=check.detail or check.label,
                evidence_refs=[f"validation:{check.check_id}"],
            )
            for check in failed_checks
        ]
        if forced_rework:
            issues.append(
                ReviewIssue(
                    severity="blocker",
                    root_cause="implementation",
                    summary="Mock Reviewer requested rework for acceptance testing",
                    evidence_refs=["reviewer:forced-rework"],
                )
            )
        warnings = list(data_profile.warnings)
        verdict = "rework" if issues else "accept"
        return ReviewReport(
            summary=f"Reviewed {app_spec.project_name} against the accepted product and engineering evidence.",
            verdict=verdict,
            requirement_checks=[f"Page covered: {page}" for page in blueprint.pages]
            + [f"Module covered: {module}" for module in blueprint.modules],
            engineering_checks=[check.label for check in validation_report.checks],
            data_findings=data_profile.insights,
            issues=issues,
            warnings=warnings,
            suggested_actions=["resolve"] if issues else (["edit"] if warnings else ["accept"]),
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
        if "minesweeper" in compact.casefold() or "扫雷" in compact:
            return "扫雷游戏" if "扫雷" in compact else "Minesweeper"
        if compact:
            return compact[:40].strip(" ，。,.!！?") or "Web Application"
        return "Mono Market"

    @staticmethod
    def _support_reason(level: SupportLevel) -> str:
        return {
            SupportLevel.SUPPORTED: "The request can run as a self-contained browser application.",
            SupportLevel.ADAPTED: (
                "The browser experience can be built after excluding unavailable server capabilities."
            ),
            SupportLevel.UNSUPPORTED: "The primary workflow requires a non-Web runtime.",
        }[level]

    @staticmethod
    def _minesweeper_code() -> tuple[str, str, str]:
        html = """<main class="game-shell">
  <header><div><span class="eyebrow">CLASSIC LOGIC GAME</span><h1>扫雷</h1><p>点击翻开方格，右键插旗，避开所有地雷。</p></div><button id="restart">重新开始</button></header>
  <section class="game-status" aria-live="polite"><strong>💣 <span id="mines-left">10</span></strong><strong id="message">准备开始</strong><strong>⏱ <span id="timer">0</span>s</strong></section>
  <section id="board" class="minefield" aria-label="扫雷棋盘"></section>
</main>"""
        css = """:root{font-family:Inter,system-ui,sans-serif;color:#17152b;background:#fff7de}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(#ded7ff 1px,transparent 1px);background-size:20px 20px}.game-shell{width:min(94vw,680px);padding:28px;border:3px solid #17152b;border-radius:18px;background:#fffaf0;box-shadow:10px 10px 0 #17152b}header{display:flex;justify-content:space-between;align-items:end;gap:20px}h1{margin:3px 0;font-size:clamp(40px,8vw,72px);line-height:.9}p{margin:10px 0 0;color:#625d72}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.12em;color:#d94f45}button{font:inherit}.game-shell>header button{padding:11px 15px;border:2px solid #17152b;border-radius:8px;background:#ffd45c;box-shadow:3px 3px 0 #17152b;font-weight:900;cursor:pointer}.game-status{display:flex;justify-content:space-between;gap:12px;margin:24px 0 14px;padding:12px 14px;border:2px solid #17152b;border-radius:10px;background:#e8f8f1}.minefield{display:grid;grid-template-columns:repeat(9,1fr);gap:4px;aspect-ratio:1}.cell{display:grid;place-items:center;min-width:0;border:2px solid #17152b;border-radius:6px;background:#ded7ff;color:#17152b;font-weight:900;font-size:clamp(12px,3vw,20px);cursor:pointer;box-shadow:2px 2px 0 #17152b}.cell:hover{transform:translate(-1px,-1px)}.cell.revealed{background:#fff;border-color:#aaa4b8;box-shadow:none;cursor:default}.cell.mine{background:#ff6f61}.cell.flagged{background:#ffd45c}@media(max-width:520px){.game-shell{padding:16px}header{align-items:start;flex-direction:column}.minefield{gap:2px}.cell{border-width:1px;border-radius:3px;box-shadow:1px 1px 0 #17152b}}"""
        javascript = """const rows=9,cols=9,mineCount=10;let mines=new Set(),revealed=new Set(),flags=new Set(),ended=false,started=false,seconds=0,tick=null;const board=document.querySelector('#board'),message=document.querySelector('#message'),timer=document.querySelector('#timer'),left=document.querySelector('#mines-left');const key=(r,c)=>r*cols+c;function neighbors(i){const r=Math.floor(i/cols),c=i%cols,out=[];for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){const nr=r+dr,nc=c+dc;if((dr||dc)&&nr>=0&&nr<rows&&nc>=0&&nc<cols)out.push(key(nr,nc))}return out}function plant(first){while(mines.size<mineCount){const value=Math.floor(Math.random()*rows*cols);if(value!==first&&!neighbors(first).includes(value))mines.add(value)}}function start(first){if(started)return;started=true;plant(first);message.textContent='进行中';tick=setInterval(()=>{seconds++;timer.textContent=String(seconds)},1000)}function reveal(i){if(ended||flags.has(i)||revealed.has(i))return;start(i);if(mines.has(i)){ended=true;clearInterval(tick);message.textContent='踩到地雷了';mines.forEach(value=>revealed.add(value));render();return}const queue=[i];while(queue.length){const current=queue.shift();if(revealed.has(current)||flags.has(current))continue;revealed.add(current);if(neighbors(current).filter(value=>mines.has(value)).length===0)queue.push(...neighbors(current))}if(revealed.size===rows*cols-mineCount){ended=true;clearInterval(tick);message.textContent='胜利！全部安全方格已清除'}render()}function flag(i){if(ended||revealed.has(i))return;flags.has(i)?flags.delete(i):flags.size<mineCount&&flags.add(i);left.textContent=String(mineCount-flags.size);render()}function render(){board.innerHTML='';for(let i=0;i<rows*cols;i++){const cell=document.createElement('button');cell.className='cell';cell.setAttribute('aria-label',`第${Math.floor(i/cols)+1}行第${i%cols+1}列`);if(flags.has(i)){cell.classList.add('flagged');cell.textContent='⚑'}if(revealed.has(i)){cell.classList.add('revealed');if(mines.has(i)){cell.classList.add('mine');cell.textContent='✹'}else{const count=neighbors(i).filter(value=>mines.has(value)).length;cell.textContent=count?String(count):''}}cell.addEventListener('click',()=>reveal(i));cell.addEventListener('contextmenu',event=>{event.preventDefault();flag(i)});board.appendChild(cell)}}function reset(){clearInterval(tick);mines=new Set();revealed=new Set();flags=new Set();ended=false;started=false;seconds=0;timer.textContent='0';left.textContent=String(mineCount);message.textContent='准备开始';render()}document.querySelector('#restart').addEventListener('click',reset);reset();"""
        return html, css, javascript

    @staticmethod
    def _generic_app_code(blueprint: Blueprint, prompt: str) -> tuple[str, str, str]:
        title = html_lib.escape(blueprint.project_name)
        modules = "".join(
            f'<button class="tool" data-tool="{index}"><strong>{html_lib.escape(module)}</strong><span>Open</span></button>'
            for index, module in enumerate(blueprint.modules)
        )
        html = (
            '<main class="app-shell"><aside><span class="eyebrow">WEB APPLICATION</span>'
            f"<h1>{title}</h1><p>{html_lib.escape(blueprint.visual_direction)}</p>"
            '<button id="reset">Reset demo state</button></aside><section class="workspace">'
            '<header><div><strong>Workspace</strong><span id="status">Ready</span></div></header>'
            f'<div class="tool-grid">{modules}</div><article id="detail"><h2>Select a feature</h2>'
            "<p>The generated interface keeps all demo state inside this browser preview.</p></article>"
            "</section></main>"
        )
        css = """:root{font-family:Inter,system-ui,sans-serif;color:#17152b;background:#fff7de}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(#ded7ff 1px,transparent 1px);background-size:20px 20px}.app-shell{min-height:100vh;display:grid;grid-template-columns:minmax(220px,300px) 1fr}aside{padding:36px 28px;border-right:3px solid #17152b;background:#e8f8f1}h1{font-size:clamp(34px,5vw,64px);line-height:.95;margin:8px 0 16px}.eyebrow{font-size:11px;font-weight:900;letter-spacing:.12em;color:#d94f45}p{color:#625d72;line-height:1.6}button{font:inherit}.tool,#reset{border:2px solid #17152b;border-radius:9px;box-shadow:3px 3px 0 #17152b;cursor:pointer}#reset{margin-top:20px;padding:10px 12px;background:#ffd45c;font-weight:800}.workspace{padding:28px}.workspace header{display:flex;justify-content:space-between;padding:16px;border:2px solid #17152b;border-radius:10px;background:#fff}.workspace header div{display:flex;justify-content:space-between;width:100%}.tool-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:20px 0}.tool{min-height:110px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;align-items:start;background:#ded7ff;text-align:left}.tool.active{background:#ff6f61}#detail{min-height:220px;padding:24px;border:2px solid #17152b;border-radius:12px;background:#fff;box-shadow:5px 5px 0 #17152b}@media(max-width:720px){.app-shell{grid-template-columns:1fr}aside{border-right:0;border-bottom:3px solid #17152b}.workspace{padding:16px}}"""
        javascript = """const tools=[...document.querySelectorAll('.tool')],detail=document.querySelector('#detail'),status=document.querySelector('#status');tools.forEach(tool=>tool.addEventListener('click',()=>{tools.forEach(item=>item.classList.remove('active'));tool.classList.add('active');const name=tool.querySelector('strong').textContent;status.textContent=`${name} active`;detail.innerHTML=`<h2>${name}</h2><p>This interactive module is running with local demo state inside the browser preview.</p><label>Demo input <input placeholder="Type to update state"></label>`}));document.querySelector('#reset').addEventListener('click',()=>{tools.forEach(item=>item.classList.remove('active'));status.textContent='Ready';detail.innerHTML='<h2>Select a feature</h2><p>The generated interface keeps all demo state inside this browser preview.</p>'});"""
        return html, css, javascript

    @staticmethod
    def _web_rewrite(prompt: str) -> str:
        """Create a deterministic Web alternative without changing the product goal."""
        normalized = prompt.lower()
        if "camera" in normalized:
            return (
                "Build a browser-based camera interface prototype that preserves the capture "
                "workflow, gallery, controls, and visual feedback, using local demo media because "
                "native device integration is outside the current Web Runtime."
            )
        return (
            "Build a browser-based version of the original product goal. Preserve its core "
            "workflow and interactions, use local client-side state, and replace only unavailable "
            "native or server capabilities with explicit demo data."
        )

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
                "Manager, Architect, Engineer, Data Analyst, and Reviewer pipeline."
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
                "Turn the request into a Web application Blueprint without changing the user's "
                "product goal. product_type is a concise free-form label such as web_game, tool, "
                "dashboard, or product_catalog; never convert a game or tool into a catalog. "
                "Use supported for self-contained browser behavior using HTML, CSS, and JavaScript. "
                "Use adapted when the visible Web experience can be built but server-side auth, "
                "payments, persistent database writes, or external services must be omitted or "
                "represented with local demo state. Use unsupported only when the primary goal "
                "cannot be represented as a Web application. Preserve the user's language and "
                "expand concrete pages, interactions, states, error feedback, and visual direction."
            ),
            {"request": prompt, "mode": mode.value},
        )

    def create_architecture_spec(self, blueprint: Blueprint) -> ArchitectureSpec:
        return self._structured_chat(
            ArchitectureSpec,
            "Architect",
            (
                "Define a self-contained browser architecture for the Blueprint. Use local client "
                "state and no generated backend, package installation, remote assets, or network "
                "calls. Describe the requested pages, components, state, and interactions. Primary "
                "text against background must meet at least 4.5:1 contrast and accent against "
                "background at least 3:1."
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
                "Produce a complete self-contained Web AppSpec. html is the semantic body fragment, "
                "css is all styling, and javascript implements the requested interactions using "
                "browser APIs. Do not use markdown fences, external URLs, remote assets, fetch, "
                "WebSocket, dynamic imports, eval, package dependencies, or backend calls. Use only "
                "inline/local content. The code must work when combined into one sandboxed HTML "
                "document. Populate pages with route/name/sections metadata matching the experience. "
                "products is optional and should only be used for an actual catalog. Copy all three "
                "colors exactly from ArchitectureSpec."
            ),
            {
                "request": prompt,
                "blueprint": blueprint.model_dump(mode="json"),
                "architecture_spec": architecture_spec.model_dump(mode="json"),
            },
        )

    def analyze_data(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        prompt: str,
    ) -> DataProfile:
        return self._structured_chat(
            DataProfile,
            "Data Analyst",
            (
                "Analyze the application's actual structured data, local state model, content records, "
                "data quality, and useful data findings. Do not perform code review or decide whether "
                "engineering validation passes. Use not_applicable when the application has no standalone "
                "dataset, and keep findings grounded in the supplied contracts."
            ),
            {
                "request": prompt,
                "blueprint": blueprint.model_dump(mode="json"),
                "architecture_spec": architecture_spec.model_dump(mode="json"),
                "app_spec": app_spec.model_dump(mode="json"),
            },
        )

    def review(
        self,
        blueprint: Blueprint,
        architecture_spec: ArchitectureSpec,
        app_spec: AppSpec,
        data_profile: DataProfile,
        validation_report: ValidationReport,
        prompt: str,
    ) -> ReviewReport:
        return self._structured_chat(
            ReviewReport,
            "Reviewer",
            (
                "Independently review whether the implementation covers the accepted Blueprint and "
                "ArchitectureSpec, using the immutable ValidationReport and DataProfile as evidence. "
                "You cannot change failed checks to pass. Return rework for unresolved blockers, "
                "needs_input only when user intent is genuinely required, otherwise accept with any "
                "non-blocking warnings. Every issue must cite an evidence reference."
            ),
            {
                "request": prompt,
                "blueprint": blueprint.model_dump(mode="json"),
                "architecture_spec": architecture_spec.model_dump(mode="json"),
                "app_spec": app_spec.model_dump(mode="json"),
                "data_profile": data_profile.model_dump(mode="json"),
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
                    "max_tokens": 8192,
                    "temperature": 0.2,
                }
                if think is not None:
                    request_body["thinking"] = {"type": "enabled" if think else "disabled"}
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
