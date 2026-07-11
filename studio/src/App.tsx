import {
  ArrowUp,
  Check,
  ChevronRight,
  CircleAlert,
  Code2,
  Download,
  ExternalLink,
  History,
  Layers3,
  LoaderCircle,
  Monitor,
  Paperclip,
  Plus,
  Rocket,
  RotateCcw,
  Smartphone,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { PreviewLoader } from "./components/PreviewApp";
import { RepositoryPanel } from "./components/RepositoryPanel";
import { AtomLogo, ROLE_META, RoleAvatar, type RoleKey } from "./components/BrandAssets";
import { api } from "./lib/api";
import type {
  AttachmentMeta,
  Blueprint,
  LeadDecisionView,
  Mode,
  ProjectView,
  QuotaView,
  ModelsView,
  RunEvent,
  RunView,
  UserView,
  VersionView,
  WorkspaceTab,
} from "./types";

const TERMINAL = new Set(["completed", "completed_degraded", "failed", "cancelled", "needs_input"]);

type Language = "zh" | "en";

const LANGUAGE_KEY = "another-atom-language";

const EXAMPLE_PROMPTS: Record<Language, string[]> = {
  zh: [
    "构建一个名为 Mono Market 的克制风格商品目录，展示精选家居用品，使用编辑感摄影和暖中性色。",
    "创建一个现代灯具系列商品站，包含首页、目录页和商品详情页，字体利落，强调色用珊瑚色。",
  ],
  en: [
    "Build a restrained product catalog called Mono Market for useful home objects. Use editorial photography and warm neutral colors.",
    "Create a modern lighting collection with Home, Catalog, and Product pages. Make the typography crisp and the accent color coral.",
  ],
};

const STAGE_LABELS: Record<Language, Record<string, string>> = {
  zh: {
    team_leader: "Lead 分派",
    product_manager: "产品经理",
    blueprint_approval: "用户确认",
    architect: "架构师",
    engineer: "工程师",
    build: "渲染器",
    data: "数据分析",
    complete: "预览就绪",
    build_queue: "构建队列",
    scope_review: "确认 PM 草案",
  },
  en: {
    team_leader: "Team Leader",
    product_manager: "Product Manager",
    blueprint_approval: "Your approval",
    architect: "Architect",
    engineer: "Engineer",
    build: "Renderer",
    data: "Data Analyst",
    complete: "Preview ready",
    build_queue: "Build queue",
    scope_review: "Confirm PM draft",
  },
};

const BUILDING_STAGE_TITLES: Record<Language, Record<string, string>> = {
  zh: {
    team_leader: "Lead 正在分派请求",
    product_manager: "产品经理正在整理需求",
    build_queue: "构建任务正在排队",
    architect: "架构师正在设计方案",
    engineer: "工程师正在生成应用规格",
    build: "渲染器正在构建页面",
    data: "数据分析正在检查结果",
    complete: "正在准备预览结果",
  },
  en: {
    team_leader: "Lead is routing the request",
    product_manager: "Product Manager is structuring the requirement",
    build_queue: "The build job is waiting to start",
    architect: "Architect is designing the solution",
    engineer: "Engineer is generating the application specification",
    build: "Renderer is building the pages",
    data: "Data Analyst is checking the result",
    complete: "Preparing the preview result",
  },
};

const ROLE_LABELS: Record<Language, Partial<Record<RoleKey, string>>> = {
  zh: {
    leader: "Lead",
    product: "产品",
    architect: "架构",
    engineer: "工程",
    data: "数据",
    renderer: "渲染",
    user: "你",
  },
  en: {},
};

const ZH: Record<string, string> = {
  "Authentication failed": "登录失败",
  "Create account": "创建账号",
  "Session Gateway": "会话网关",
  "Create your workspace": "创建你的工作区",
  "Sign in": "登录",
  "Projects, repositories, versions, and Sandbox sessions stay isolated by account.": "项目、源码仓库、版本和 Sandbox Session 都按账号隔离。",
  "Display name": "显示名称",
  "Username": "用户名",
  "Password": "密码",
  "Already have an account? Sign in": "已有账号？登录",
  "Need an account? Sign up": "没有账号？注册",
  "Could not start the run": "无法启动任务",
  "Could not open the project": "无法打开项目",
  "Lead request sent to {model}. Waiting for model response.": "已发送给 Lead（{model}），等待模型返回。",
  "Lead is producing a direct/team decision": "Lead 正在生成 direct/team 路由决策",
  "Project and Run logs start after this step completes.": "此步骤完成后才会创建 Project，并接入 Run 日志。",
  "Model response is slower than usual.": "模型响应比平时慢，仍在等待服务端返回。",
  "Ollama timed out. Switching provider to DeepSeek official API…": "Ollama 响应超时，服务商切换中：DeepSeek 官方 API……",
  "Provider fallback completed: {provider}.": "服务商切换完成：{provider}。",
  "seconds": "秒",
  "Lead routed this message to {route}.": "Lead 将消息路由到 {route}。",
  "No build run was created because Lead answered directly.": "Lead 已直接回答，没有创建构建任务。",
  "Creating Project and Build Run.": "正在创建项目和构建任务。",
  "Run created. Opening build event stream.": "任务已创建，正在打开构建事件流。",
  "Project workspace": "项目工作区",
  "Application studio": "应用工作台",
  "New project": "新建项目",
  "Projects": "项目",
  "Your generated projects will appear here.": "生成的项目会显示在这里。",
  "Demo usage": "演示配额",
  "left": "剩余",
  "LLM usage is isolated to this account.": "LLM 用量按当前账号隔离。",
  "Sign out": "退出登录",
  "Real LLM is active": "真实 LLM 已启用",
  "Mock LLM is active": "Mock LLM 已启用",
  "Your build team": "你的构建团队",
  "Talk to Lead": "和 Lead 对话",
  "Ask a question, clarify the scope, or explicitly request a product catalog build.": "可以询问、澄清范围，或明确要求构建商品目录。",
  "A product catalog called Mono Market for carefully selected home objects…": "一个名为 Mono Market 的精选家居商品目录……",
  "Add reference attachments": "添加参考附件",
  "Language model": "语言模型",
  "Send to Lead": "发送给 Lead",
  "Remove attachment": "移除附件",
  "Call team": "调用团队",
  "Lead handoff": "Lead 交接",
  "Submit a message to see pre-project Lead progress. Project logs appear after a Run is created.": "提交消息后会显示项目创建前的 Lead 进度；任务创建后日志进入项目。",
  "Start with an example": "从示例开始",
  "Staged pipeline": "阶段流水线",
  "Build activity": "构建活动",
  "Team pipeline": "团队流水线",
  "Engineer pipeline": "工程流水线",
  "In progress": "进行中",
  "Complete": "已完成",
  "Waiting": "等待中",
  "Waiting for your input": "等待你确认",
  "Project log": "项目日志",
  "Run": "任务",
  "Run log": "运行日志",
  "Download log": "下载日志",
  "Recent events": "最近事件",
  "No persisted events yet.": "暂无持久化事件。",
  "Latest": "最新",
  "persisted event": "条持久化事件",
  "persisted events": "条持久化事件",
  "Scope needs revision": "等待确认可构建替代方案",
  "The team stopped before build because the request needs to be narrowed.": "原始产品目标超出 V1 商品目录范围，不能按原请求直接构建。",
  "No build job was created": "确认草案后开始构建",
  "Rewrite": "PM 草案",
  "Waiting for approval": "等待确认",
  "The Blueprint changes the requested scope, so the build is paused until you confirm it.": "Blueprint 对请求范围做了调整，确认前不会继续构建。",
  "Blueprint ready": "Blueprint 已就绪",
  "Preview version is ready": "预览版本已就绪",
  "The run created a ProjectVersion. Publishing still requires an explicit user action.": "本次任务已创建项目版本；发布仍需要用户显式操作。",
  "Version created": "版本已创建",
  "Run stopped with an error": "任务因错误停止",
  "The run failed before producing a ready preview.": "任务在生成可预览版本前失败。",
  "The controlled renderer rejected the generated AppSpec": "生成结果未通过受控构建校验。",
  "Primary/background contrast is below 4.5:1": "主色与背景色的对比度低于 4.5:1。",
  "Accent/background contrast is below 3:1": "强调色与背景色的对比度低于 3:1。",
  "AppSpec colors do not match the approved ArchitectureSpec tokens": "应用颜色与架构阶段确认的视觉 Token 不一致。",
  "No deterministic evidence for: Editable visual direction": "缺少“可编辑视觉方向”的确定性校验证据。",
  "Failed validation checks": "未通过的校验项",
  "Retry with saved request": "使用已保存需求重新构建",
  "Retrying creates a new Run and preserves this failure record.": "重新构建会创建新任务，并保留本次失败记录。",
  "Failure recorded": "失败已记录",
  "Build is moving": "构建进行中",
  "The run has started and is waiting for the next persisted event.": "任务已启动，正在等待下一条持久化事件。",
  "Blueprint": "Blueprint",
  "Human-in-the-loop · Adapted scope": "人工确认 · 范围调整",
  "Confirm the scope change": "确认范围变化",
  "The supported catalog can continue only after you accept the omitted requirements.": "接受被省略的需求后，受支持的商品目录才能继续构建。",
  "Some requirements were adapted": "部分需求已被调整",
  "Project name": "项目名称",
  "Visual direction": "视觉方向",
  "Pages": "页面",
  "Modules": "模块",
  "Mapped requirements": "已映射需求",
  "Accept the adapted scope?": "接受调整后的范围？",
  "This records an explicit risk confirmation.": "这会记录一次明确的风险确认。",
  "Confirm & build": "确认并构建",
  "Product Manager feedback": "产品经理反馈",
  "The original product cannot be built in V1. Product Manager created a catalog alternative that keeps only its theme.": "原始产品目标无法在 V1 构建。产品经理只保留主题，生成了一个商品目录替代方案。",
  "Confirm the catalog alternative": "确认商品目录替代方案",
  "This alternative changes the product type. Accept it only if you want a catalog instead of the original application.": "该方案会改变产品类型。只有当你接受用商品目录替代原应用时才继续。",
  "Buildable alternative": "可构建替代方案（会改变产品目标）",
  "Accept alternative & build": "接受替代方案并开始构建",
  "Regenerate requirement draft": "让 PM 重新生成需求草案",
  "Product Manager will reinterpret the text and return a new catalog alternative without starting a build.": "产品经理会重新理解输入并生成新的商品目录替代草案，不会开始构建。",
  "The confirmed draft must remain a product catalog. To reinterpret a game or another product type, regenerate the requirement first.": "确认构建的草案必须仍是商品目录。如果要重新解释游戏或其他产品类型，请先让 PM 重新生成需求草案。",
  "Could not regenerate the requirement draft": "无法重新生成需求草案",
  "Confirmation skips Product Manager and continues directly to architecture.": "确认后不会再次调用产品经理，将直接进入架构阶段。",
  "Describe a product catalog with Home, Catalog, and Product pages…": "描述一个包含首页、目录页和商品详情页的商品目录……",
  "Run stopped": "任务已停止",
  "Your project and original request are still saved.": "项目和原始请求仍已保存。",
  "Build queued": "构建已排队",
  "is working": "正在工作",
  "The current stage is persisted. Refreshing this page will not lose the run.": "当前阶段已持久化，刷新页面不会丢失本次任务。",
  "Save failed": "保存失败",
  "Publish failed": "发布失败",
  "Preview": "预览",
  "Edit": "编辑",
  "Vim": "Vim",
  "Versions": "版本",
  "Desktop preview": "桌面预览",
  "Mobile preview": "移动端预览",
  "Publish": "发布",
  "Published successfully": "发布成功",
  "Open public app": "打开公开应用",
  "Generated application preview": "生成应用预览",
  "Structured edit": "结构化编辑",
  "Refine the current version": "调整当前版本",
  "Saving creates a new ProjectVersion and keeps the original.": "保存会创建新的项目版本，原版本不会被覆盖。",
  "Hero title": "首屏标题",
  "Hero body": "首屏正文",
  "Primary color": "主色",
  "Save as new version": "保存为新版本",
  "Project history": "项目历史",
  "Restore always creates a new version; history is never overwritten.": "恢复会创建新版本，历史不会被覆盖。",
  "Current": "当前",
  "Restore": "恢复",
  "supported": "支持",
  "adapted": "需确认",
  "unsupported": "不支持",
  "direct": "直接回答",
  "team": "调用团队",
  "completed": "已完成",
  "completed_degraded": "已完成，有警告",
  "failed": "失败",
  "cancelled": "已取消",
  "needs_input": "等待确认需求",
  "draft": "草稿",
  "ready": "就绪",
  "live": "已发布",
  "paused": "已暂停",
  "awaiting_approval": "等待确认",
  "product_running": "产品阶段",
  "build_queued": "构建排队",
  "architect_running": "架构阶段",
  "engineer_running": "工程阶段",
  "building": "构建中",
  "data_running": "数据阶段",
  "Product Manager is structuring the request": "产品经理正在整理需求",
  "Blueprint is ready for review": "Blueprint 已生成，等待检查",
  "The request is outside the V1 catalog scope": "请求超出 V1 商品目录范围",
  "V1 only supports product catalog sites (Home, Catalog, Product pages), not interactive games.": "V1 当前只支持商品目录站点（首页、目录页、商品详情页），不支持交互式游戏。",
  "Describe a product showcase or catalog with Home, Catalog, and Product pages.": "描述一个包含首页、目录页和商品详情页的商品展示或目录。",
  "To use V1, consider creating a product catalog for a board game store, featuring minesweeper-themed products, with Home, Catalog, and Product pages.": "建议改成：创建一个扫雷主题商品目录，展示桌游或周边商品，包含首页、目录页和商品详情页。",
  "Review and confirm the Blueprint before building": "构建前需要检查并确认 Blueprint",
  "Supported Blueprint is within the requested scope and base budget": "受支持 Blueprint 在请求范围和基础预算内",
  "Build is queued": "构建已进入队列",
  "Architect is defining structure, data boundaries, and visual tokens": "架构师正在定义结构、数据边界和视觉 Token",
  "ArchitectureSpec passed schema validation": "ArchitectureSpec 已通过结构校验",
  "Engineer is producing the renderer contract": "工程师正在生成渲染器 Contract",
  "AppSpec passed schema validation": "AppSpec 已通过结构校验",
  "Controlled React renderer started": "受控 React 渲染器已启动",
  "Deterministic route, data, and renderer checks completed": "路由、数据和渲染器确定性校验已完成",
  "Data Analyst is checking catalog data and validation evidence": "数据分析正在检查商品数据和校验证据",
  "DataReview is ready": "DataReview 已生成",
  "Interactive preview is ready": "可交互预览已就绪",
  "The build worker stopped unexpectedly": "Build Worker 异常停止",
  "event.run.created": "任务已创建",
  "event.stage.started": "阶段已开始",
  "event.artifact.created": "产物已保存",
  "event.approval.required": "等待确认",
  "event.run.needs_input": "需要补充输入",
  "event.run.completed": "任务已完成",
  "event.run.failed": "任务失败",
  "event.provider.fallback": "服务商已切换",
  "Ollama timed out; switched to DeepSeek official API": "Ollama 超时，已切换到 DeepSeek 官方 API",
};

type ActivityEntry = {
  id: string;
  message: string;
  tone: "pending" | "success" | "error";
};

function ui(language: Language, text: string): string {
  return language === "zh" ? ZH[text] ?? text : text;
}

function template(
  language: Language,
  text: string,
  values: Record<string, string>,
): string {
  return Object.entries(values).reduce(
    (current, [key, value]) => current.replaceAll(`{${key}}`, value),
    ui(language, text),
  );
}

function stageLabel(language: Language, stage: string): string {
  return STAGE_LABELS[language][stage] ?? stage;
}

function roleLabel(language: Language, role: RoleKey): string {
  return ROLE_LABELS[language][role] ?? ROLE_META[role].label;
}

function statusLabel(language: Language, status: string): string {
  return ui(language, status).replaceAll("_", " ");
}

function routeLabel(language: Language, route: string): string {
  return ui(language, route);
}

function displayText(language: Language, value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "";
  return ui(language, value.trim());
}

function conversationalText(language: Language, value: unknown, fallback: string): string {
  const raw = typeof value === "string" ? value.trim() : "";
  const text = displayText(language, raw);
  const containsChinese = /[\u3400-\u9fff]/.test(raw);
  if (language === "zh" && raw && text === raw && !containsChinese && /[A-Za-z]{4,}/.test(raw)) return ui(language, fallback);
  return text || ui(language, fallback);
}

function eventTitle(language: Language, event: RunEvent): string {
  const key = `event.${event.type}`;
  const title = ui(language, key);
  return title === key ? event.type : title;
}

function eventMessage(language: Language, event: RunEvent): string {
  return displayText(language, event.payload.message ?? event.type) || eventTitle(language, event);
}

function rewriteSuggestion(language: Language, blueprint: Blueprint | null, events: RunEvent[]): string {
  const latestRewrite = [...events].reverse().find((event) => typeof event.payload.rewrite_suggestion === "string")?.payload.rewrite_suggestion;
  return conversationalText(language, blueprint?.rewrite_suggestion ?? latestRewrite, "Describe a product catalog with Home, Catalog, and Product pages…");
}

function isCatalogAlternative(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return ["商品", "商城", "商店", "product catalog", "storefront", "catalog site", "product store", "shop"]
    .some((marker) => normalized.includes(marker));
}

function LanguageToggle({
  language,
  setLanguage,
}: {
  language: Language;
  setLanguage: (language: Language) => void;
}) {
  return <div className="language-toggle" aria-label={language === "zh" ? "语言切换" : "Language switch"}>
    <button className={language === "zh" ? "active" : ""} onClick={() => setLanguage("zh")}>中文</button>
    <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
  </div>;
}

export function App() {
  const previewMatch = window.location.pathname.match(/^\/preview\/([^/]+)/);
  const publicMatch = window.location.pathname.match(/^\/apps\/([^/]+)/);
  if (previewMatch) return <PreviewLoader kind="preview" id={previewMatch[1]} />;
  if (publicMatch) return <PreviewLoader kind="public" id={publicMatch[1]} />;
  return <Studio />;
}

function AuthView({
  onAuthenticated,
  language,
  setLanguage,
}: {
  onAuthenticated: (user: UserView) => void;
  language: Language;
  setLanguage: (language: Language) => void;
}) {
  const [signup, setSignup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const submit = async () => {
    setSubmitting(true);
    setError("");
    try {
      onAuthenticated(signup
        ? await api.signup(username, password, displayName)
        : await api.login(username, password));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Authentication failed"));
    } finally {
      setSubmitting(false);
    }
  };
  return <main className="auth-view">
    <div className="auth-card">
      <div className="auth-head"><div className="brand"><AtomLogo /><strong>Another Atom</strong></div><LanguageToggle language={language} setLanguage={setLanguage} /></div>
      <span>{ui(language, signup ? "Create account" : "Session Gateway")}</span>
      <h1>{ui(language, signup ? "Create your workspace" : "Sign in")}</h1>
      <p>{ui(language, "Projects, repositories, versions, and Sandbox sessions stay isolated by account.")}</p>
      {signup && <label>{ui(language, "Display name")}<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" /></label>}
      <label>{ui(language, "Username")}<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
      <label>{ui(language, "Password")}<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={signup ? "new-password" : "current-password"} /></label>
      {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
      <button className="primary-action" disabled={submitting || username.length < 3 || password.length < 10} onClick={submit}>{submitting && <LoaderCircle className="spin" size={16} />}{ui(language, signup ? "Create account" : "Sign in")}</button>
      <button className="auth-switch" onClick={() => setSignup((value) => !value)}>{ui(language, signup ? "Already have an account? Sign in" : "Need an account? Sign up")}</button>
    </div>
  </main>;
}

function Studio() {
  const [language, setLanguageState] = useState<Language>(() => window.localStorage.getItem(LANGUAGE_KEY) === "en" ? "en" : "zh");
  const [user, setUser] = useState<UserView | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [attachments, setAttachments] = useState<AttachmentMeta[]>([]);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [versions, setVersions] = useState<VersionView[]>([]);
  const [quota, setQuota] = useState<QuotaView | null>(null);
  const [models, setModels] = useState<ModelsView | null>(null);
  const [model, setModel] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [leadDecision, setLeadDecision] = useState<LeadDecisionView | null>(null);
  const [activityLog, setActivityLog] = useState<ActivityEntry[]>([]);
  const [leadElapsed, setLeadElapsed] = useState(0);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [tab, setTab] = useState<WorkspaceTab>("preview");

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    window.localStorage.setItem(LANGUAGE_KEY, nextLanguage);
  };

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null)).finally(() => setAuthChecked(true));
  }, []);

  const refreshShell = useCallback(async () => {
    const [nextProjects, nextQuota] = await Promise.all([api.projects(), api.quota()]);
    setProjects(nextProjects);
    setQuota(nextQuota);
  }, []);

  const refreshRun = useCallback(async (runId: string) => {
    const [nextRun, nextEvents] = await Promise.all([api.getRun(runId), api.events(runId)]);
    setRun(nextRun);
    setEvents(nextEvents);
    if (nextRun.version_id) {
      setVersions(await api.versions(nextRun.project_id));
    }
    return nextRun;
  }, []);

  useEffect(() => {
    if (!user) return;
    const loadShell = async () => refreshShell();
    void loadShell().catch(() => undefined);
  }, [refreshShell, user]);
  useEffect(() => {
    api.models().then((result) => {
      setModels(result);
      setModel((current) => current || result.default_model);
    }).catch((reason: Error) => setError(reason.message));
  }, []);
  const activeRunId = run?.run_id;
  const activeRunStatus = run?.status;
  useEffect(() => {
    if (!activeRunId || !activeRunStatus || TERMINAL.has(activeRunStatus)) return;
    const source = new EventSource(`/api/runs/${activeRunId}/events`);
    const eventTypes = [
      "stage.started",
      "stage.completed",
      "artifact.created",
      "agent.retry",
      "approval.required",
      "approval.confirmed",
      "build.auto_authorized",
      "build.queued",
      "build.started",
      "validation.completed",
      "provider.fallback",
      "run.needs_input",
      "run.completed",
      "run.failed",
    ];
    const receive = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as RunEvent;
      setEvents((current) => {
        if (current.some((item) => item.event_id === event.event_id)) return current;
        return [...current, event].sort((left, right) => left.sequence - right.sequence);
      });
    };
    eventTypes.forEach((eventType) => source.addEventListener(eventType, receive as EventListener));
    return () => source.close();
  }, [activeRunId, activeRunStatus]);
  useEffect(() => {
    if (!run || TERMINAL.has(run.status) || run.status === "awaiting_approval") return;
    const timer = window.setInterval(() => {
      refreshRun(run.run_id).then((next) => {
        if (TERMINAL.has(next.status)) refreshShell().catch(() => undefined);
      }).catch((reason: Error) => setError(reason.message));
    }, 700);
    return () => window.clearInterval(timer);
  }, [refreshRun, refreshShell, run]);

  const sendToLead = async (forceTeam = false) => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setError("");
    setActivityLog([
      {
        id: `${Date.now()}-lead-started`,
        message: template(language, "Lead request sent to {model}. Waiting for model response.", { model }),
        tone: "pending",
      },
    ]);
    const leadStartedAt = Date.now();
    setLeadElapsed(0);
    const leadTimer = window.setInterval(() => {
      setLeadElapsed(Math.floor((Date.now() - leadStartedAt) / 1000));
    }, 1000);
    const appendActivity = (message: string, tone: ActivityEntry["tone"] = "pending") => {
      setActivityLog((current) => [...current, { id: `${Date.now()}-${current.length}`, message, tone }]);
    };
    try {
      const decision = await api.leadMessage(prompt, model, forceTeam);
      window.clearInterval(leadTimer);
      setLeadDecision(decision);
      if (decision.fallback_provider) {
        appendActivity(template(language, "Provider fallback completed: {provider}.", { provider: decision.fallback_provider }), "success");
      }
      appendActivity(template(language, "Lead routed this message to {route}.", { route: routeLabel(language, decision.route) }), "success");
      if (decision.route === "direct") {
        appendActivity(ui(language, "No build run was created because Lead answered directly."), "success");
        await refreshShell();
        return;
      }
      appendActivity(ui(language, "Creating Project and Build Run."), "pending");
      const created = await api.createRun(prompt, "team", model, attachments);
      setRun(created);
      appendActivity(ui(language, "Run created. Opening build event stream."), "success");
      setEvents(await api.events(created.run_id));
      setVersions([]);
      await refreshShell();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Could not start the run"));
      appendActivity(reason instanceof Error ? reason.message : ui(language, "Could not start the run"), "error");
    } finally {
      window.clearInterval(leadTimer);
      setSubmitting(false);
    }
  };

  const openProject = async (project: ProjectView) => {
    setError("");
    try {
      const latest = await api.latestRun(project.id);
      setRun(latest);
      setPrompt("");
      setEvents(await api.events(latest.run_id));
      setVersions(await api.versions(project.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Could not open the project"));
    }
  };

  const resetComposer = () => {
    setRun(null);
    setEvents([]);
    setVersions([]);
    setPrompt("");
    setAttachments([]);
    setError("");
    setLeadDecision(null);
    setActivityLog([]);
  };

  if (!authChecked) return <div className="auth-loading"><LoaderCircle className="spin" /></div>;
  if (!user) return <AuthView onAuthenticated={setUser} language={language} setLanguage={setLanguage} />;

  return (
    <div className="studio-shell">
      <Sidebar
        projects={projects}
        quota={quota}
        activeProjectId={run?.project_id}
        user={user}
        language={language}
        onNew={resetComposer}
        onOpen={openProject}
        onLogout={async () => {
          await api.logout();
          setRun(null);
          setProjects([]);
          setUser(null);
        }}
      />
      <main className={run ? "studio-main active" : "studio-main"}>
        <header className="studio-topbar">
          <div>
            <span className="topbar-context">{ui(language, run ? "Project workspace" : "Application studio")}</span>
            <strong>{run?.blueprint?.project_name ?? "Another Atom"}</strong>
          </div>
          <div className="topbar-actions">
            {run && <div className="topbar-status"><span className="model-badge"><Sparkles size={13} /> {run.model}</span><StatusPill status={run.status} language={language} /></div>}
            <LanguageToggle language={language} setLanguage={setLanguage} />
          </div>
        </header>
        {!run ? (
          <Composer
            prompt={prompt}
            setPrompt={setPrompt}
            model={model}
            setModel={setModel}
            models={models}
            attachments={attachments}
            setAttachments={setAttachments}
            submitting={submitting}
            error={error}
            leadDecision={leadDecision}
            activityLog={activityLog}
            leadElapsed={leadElapsed}
            language={language}
            sendToLead={sendToLead}
          />
        ) : (
          <Workspace
            key={run.run_id}
            run={run}
            setRun={setRun}
            events={events}
            versions={versions}
            setVersions={setVersions}
            device={device}
            setDevice={setDevice}
            tab={tab}
            setTab={setTab}
            refreshShell={refreshShell}
            refreshRun={refreshRun}
            error={error}
            setError={setError}
            sandboxAvailable={models?.sandbox_available ?? false}
            language={language}
          />
        )}
      </main>
    </div>
  );
}

function Sidebar({
  projects,
  quota,
  activeProjectId,
  user,
  language,
  onNew,
  onOpen,
  onLogout,
}: {
  projects: ProjectView[];
  quota: QuotaView | null;
  activeProjectId?: string;
  user: UserView;
  language: Language;
  onNew: () => void;
  onOpen: (project: ProjectView) => void;
  onLogout: () => void;
}) {
  return (
    <aside className="studio-sidebar">
      <div className="brand"><AtomLogo /><strong>Another Atom</strong></div>
      <button className="new-project" onClick={onNew}><Plus size={17} /> {ui(language, "New project")}</button>
      <div className="sidebar-section">
        <span className="sidebar-label">{ui(language, "Projects")}</span>
        <div className="project-list">
          {projects.length === 0 && <p className="sidebar-empty">{ui(language, "Your generated projects will appear here.")}</p>}
          {projects.map((project) => (
            <button
              key={project.id}
              className={project.id === activeProjectId ? "project-link active" : "project-link"}
              onClick={() => onOpen(project)}
            >
              <span className="project-icon"><Layers3 size={15} /></span>
              <span><strong>{project.name}</strong><small>{statusLabel(language, project.status)}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      </div>
      <div className="quota-panel">
        <div><span>{ui(language, "Demo usage")}</span><strong>{quota?.remaining ?? "–"} {ui(language, "left")}</strong></div>
        <div className="quota-track"><span style={{ width: `${quota ? (quota.used / quota.limit) * 100 : 0}%` }} /></div>
        <small>{ui(language, "LLM usage is isolated to this account.")}</small>
      </div>
      <button className="account-button" onClick={onLogout}><span>{user.display_name}</span><small>{ui(language, "Sign out")}</small></button>
    </aside>
  );
}

function Composer({
  prompt,
  setPrompt,
  model,
  setModel,
  models,
  attachments,
  setAttachments,
  submitting,
  error,
  leadDecision,
  activityLog,
  leadElapsed,
  language,
  sendToLead,
}: {
  prompt: string;
  setPrompt: (value: string) => void;
  model: string;
  setModel: (model: string) => void;
  models: ModelsView | null;
  attachments: AttachmentMeta[];
  setAttachments: (items: AttachmentMeta[]) => void;
  submitting: boolean;
  error: string;
  leadDecision: LeadDecisionView | null;
  activityLog: ActivityEntry[];
  leadElapsed: number;
  language: Language;
  sendToLead: (forceTeam?: boolean) => void;
}) {
  const addFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []).slice(0, 5 - attachments.length);
    setAttachments([
      ...attachments,
      ...files.map((file) => ({ name: file.name, size: file.size, content_type: file.type || "application/octet-stream" })),
    ]);
    event.target.value = "";
  };
  return (
    <section className="composer-view">
      <div className="composer-heading">
        <span className="notice"><Sparkles size={14} /> {ui(language, models?.provider === "ollama" ? "Real LLM is active" : "Mock LLM is active")}</span>
        <div className="crew-stage" aria-label={ui(language, "Your build team")}>
          <span className="crew-spark spark-one" />
          <span className="crew-spark spark-two" />
          {(["leader", "product", "architect", "engineer", "data"] as RoleKey[]).map((role) => (
            <div className="crew-member" key={role}>
              <RoleAvatar role={role} size="large" />
              <span>{roleLabel(language, role)}</span>
            </div>
          ))}
        </div>
        <h1>{ui(language, "Talk to Lead")}</h1>
        <p>{ui(language, "Ask a question, clarify the scope, or explicitly request a product catalog build.")}</p>
      </div>
      <div className="composer-layout">
        <div className="composer-primary">
          <div className="composer-box">
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={ui(language, "A product catalog called Mono Market for carefully selected home objects…")}
              maxLength={4000}
              autoFocus
            />
            {attachments.length > 0 && (
              <div className="attachment-row">
                {attachments.map((attachment) => (
                  <span key={attachment.name}><Paperclip size={13} /> {attachment.name}<button aria-label={`${ui(language, "Remove attachment")} ${attachment.name}`} title={ui(language, "Remove attachment")} onClick={() => setAttachments(attachments.filter((item) => item !== attachment))}><X size={13} /></button></span>
                ))}
              </div>
            )}
            <div className="composer-actions">
              <label className="attach-button" title={ui(language, "Add reference attachments")}><Paperclip size={17} /><input type="file" multiple onChange={addFiles} /></label>
              <label className="model-select">
                <Sparkles size={14} />
                <select value={model} onChange={(event) => setModel(event.target.value)} aria-label={ui(language, "Language model")}>
                  {(models?.models ?? []).map((option) => <option value={option.id} key={option.id}>{option.label}</option>)}
                </select>
              </label>
              <button className="submit-prompt" disabled={!prompt.trim() || !model || submitting} onClick={() => sendToLead()} aria-label={ui(language, "Send to Lead")} title={ui(language, "Send to Lead")}>
                {submitting ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={19} />}
              </button>
            </div>
          </div>
          {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
          {leadDecision?.route === "direct" && <div className="lead-reply"><RoleAvatar role="leader" size="small" /><div><strong>Lead</strong><p>{leadDecision.response}</p><small>{leadDecision.reason}</small></div><button onClick={() => sendToLead(true)}>{ui(language, "Call team")}</button></div>}
        </div>
        <ActivityLog entries={activityLog} active={submitting} elapsed={leadElapsed} fallbackProvider={models?.fallback_provider ?? null} language={language} />
      </div>
      <div className="example-prompts">
        <span>{ui(language, "Start with an example")}</span>
        {EXAMPLE_PROMPTS[language].map((example, index) => <button key={example} onClick={() => setPrompt(example)}><span>0{index + 1}</span>{example}</button>)}
      </div>
    </section>
  );
}

function ActivityLog({ entries, active, elapsed, fallbackProvider, language }: { entries: ActivityEntry[]; active: boolean; elapsed: number; fallbackProvider: string | null; language: Language }) {
  return <aside className="activity-panel" aria-live="polite">
    <div className="activity-heading">
      <span>{ui(language, "Lead handoff")}</span>
      {active && <LoaderCircle className="spin" size={14} />}
    </div>
    {entries.length === 0 ? (
      <p className="activity-empty">{ui(language, "Submit a message to see pre-project Lead progress. Project logs appear after a Run is created.")}</p>
    ) : (
      <div className="activity-list">
        {entries.map((entry) => <div className={`activity-item ${entry.tone}`} key={entry.id}><i /> <p>{entry.message}</p></div>)}
      </div>
    )}
    {active && <div className="lead-wait-log">
      <div><LoaderCircle className="spin" size={14} /><strong>{ui(language, "Lead is producing a direct/team decision")}</strong><time>{elapsed} {ui(language, "seconds")}</time></div>
      <p>{ui(language, "Project and Run logs start after this step completes.")}</p>
      {fallbackProvider && elapsed >= 30
        ? <small>{ui(language, "Ollama timed out. Switching provider to DeepSeek official API…")}</small>
        : elapsed >= 15 && <small>{ui(language, "Model response is slower than usual.")}</small>}
    </div>}
  </aside>;
}

function Workspace({
  run,
  setRun,
  events,
  versions,
  setVersions,
  device,
  setDevice,
  tab,
  setTab,
  refreshShell,
  refreshRun,
  error,
  setError,
  sandboxAvailable,
  language,
}: {
  run: RunView;
  setRun: (run: RunView) => void;
  events: RunEvent[];
  versions: VersionView[];
  setVersions: (versions: VersionView[]) => void;
  device: "desktop" | "mobile";
  setDevice: (device: "desktop" | "mobile") => void;
  tab: WorkspaceTab;
  setTab: (tab: WorkspaceTab) => void;
  refreshShell: () => Promise<void>;
  refreshRun: (runId: string) => Promise<RunView>;
  error: string;
  setError: (error: string) => void;
  sandboxAvailable: boolean;
  language: Language;
}) {
  const [approving, setApproving] = useState(false);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(run.blueprint);
  const ready = run.status === "completed" || run.status === "completed_degraded";

  const approve = async () => {
    if (!blueprint) return;
    setApproving(true);
    setError("");
    try {
      const queued = await api.approve(run.run_id, blueprint);
      setRun(queued);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  };

  return (
    <div className="workspace-grid">
      <section className="workspace-process">
        <div className="panel-heading"><div><span>{ui(language, "Staged pipeline")}</span><h2>{ui(language, "Build activity")}</h2></div><ModeBadge mode={run.mode} language={language} /></div>
        <Timeline run={run} events={events} language={language} />
        {run.blueprint && run.status !== "awaiting_approval" && <BlueprintSnapshot blueprint={run.blueprint} language={language} />}
        {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
      </section>
      <section className="workspace-content">
        {run.status === "awaiting_approval" && blueprint ? (
          <BlueprintEditor blueprint={blueprint} setBlueprint={setBlueprint} approve={approve} approving={approving} language={language} />
        ) : run.status === "needs_input" ? (
          <ScopeStop blueprint={blueprint} events={events} run={run} setRun={setRun} refreshShell={refreshShell} setError={setError} language={language} />
        ) : run.status === "failed" ? (
          <FailedState run={run} setRun={setRun} refreshShell={refreshShell} setError={setError} language={language} />
        ) : ready && run.version_id ? (
          <ResultWorkspace
            key={run.version_id}
            run={run}
            versions={versions}
            setVersions={setVersions}
            device={device}
            setDevice={setDevice}
            tab={tab}
            setTab={setTab}
            refreshShell={refreshShell}
            refreshRun={refreshRun}
            setError={setError}
            language={language}
          />
        ) : (
          <BuildingState run={run} language={language} />
        )}
      </section>
      <RepositoryPanel run={run} events={events} language={language} sandboxAvailable={sandboxAvailable} logPanel={<RunLogPanel run={run} events={events} language={language} />} onError={setError} onVersionSaved={async (version) => { setVersions([version, ...versions]); await refreshRun(run.run_id); await refreshShell(); }} />
    </div>
  );
}

function Timeline({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const requiresApproval = run.status === "awaiting_approval" || run.blueprint?.support_level === "adapted";
  const needsInput = run.status === "needs_input";
  const stages = run.mode === "team"
    ? ["team_leader", "product_manager", ...(needsInput ? ["scope_review"] : requiresApproval ? ["blueprint_approval"] : []), "architect", "engineer", "build", "data", "complete"]
    : ["product_manager", ...(needsInput ? ["scope_review"] : requiresApproval ? ["blueprint_approval"] : []), "engineer", "build", "complete"];
  const roles: Record<string, RoleKey> = { team_leader: "leader", product_manager: "product", scope_review: "user", blueprint_approval: "user", architect: "architect", engineer: "engineer", build: "renderer", data: "data", complete: "data" };
  const displayStage = run.current_stage === "build_queue" ? "engineer" : run.current_stage;
  const currentIndex = stages.indexOf(displayStage);
  return <div className="timeline">
    {stages.map((stage, index) => {
      const completed = currentIndex > index || TERMINAL.has(run.status) && run.status.startsWith("completed");
      const active = displayStage === stage;
      const state = active && needsInput ? "Waiting for your input" : active ? "In progress" : completed ? "Complete" : "Waiting";
      return <div className={active ? "timeline-item active" : completed ? "timeline-item complete" : "timeline-item"} key={stage}>
        <div className="timeline-avatar"><RoleAvatar role={roles[stage]} size="small" /><span className="timeline-state">{completed ? <Check size={10} /> : active && needsInput ? <CircleAlert size={10} /> : active ? <LoaderCircle className="spin" size={10} /> : index + 1}</span></div>
        <div><strong>{stageLabel(language, stage)}</strong><small>{ui(language, state)}</small></div>
      </div>;
    })}
    <ProjectLog run={run} events={events} language={language} />
  </div>;
}

function ProjectLog({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const latest = events.at(-1);
  const summary = summarizeProjectLog(run, events, language);
  return <div className={`project-log ${summary.tone}`}>
    <div className="project-log-heading">
      <span>{ui(language, "Project log")}</span>
      <small>{ui(language, "Run")} {run.run_id.slice(0, 8)}</small>
    </div>
    <strong>{summary.title}</strong>
    <p>{summary.detail}</p>
    <div className="project-log-facts">
      {summary.facts.map((fact) => <span key={fact}>{fact}</span>)}
    </div>
    <div className="event-log">
      <span>{ui(language, "Recent events")}</span>
      {events.length === 0 ? <p>{ui(language, "No persisted events yet.")}</p> : events.slice(-5).reverse().map((event) => <div key={event.event_id}><i /> <p><strong>{eventTitle(language, event)}</strong><span>{eventMessage(language, event)}</span></p></div>)}
      {latest && <small>{ui(language, "Latest")}: {new Date(latest.timestamp).toLocaleTimeString()}</small>}
    </div>
  </div>;
}

function summarizeProjectLog(run: RunView, events: RunEvent[], language: Language): { title: string; detail: string; facts: string[]; tone: "running" | "success" | "warning" | "error" } {
  const latest = events.at(-1);
  const facts = [
    `${events.length} ${ui(language, events.length === 1 ? "persisted event" : "persisted events")}`,
    stageLabel(language, run.current_stage),
  ];
  if (run.status === "needs_input") {
    const reason = conversationalText(language, run.blueprint?.support_reasons[0] ?? latest?.payload.message, "The team stopped before build because the request needs to be narrowed.");
    const rewrite = rewriteSuggestion(language, run.blueprint, events);
    return {
      title: ui(language, "Scope needs revision"),
      detail: reason,
      facts: [...facts, rewrite ? `${ui(language, "Rewrite")}: ${rewrite}` : ui(language, "No build job was created")],
      tone: "warning",
    };
  }
  if (run.status === "awaiting_approval") {
    return {
      title: ui(language, "Waiting for approval"),
      detail: ui(language, "The Blueprint changes the requested scope, so the build is paused until you confirm it."),
      facts: [...facts, run.blueprint?.support_level ? `${ui(language, "Blueprint")}: ${ui(language, run.blueprint.support_level)}` : ui(language, "Blueprint ready")],
      tone: "warning",
    };
  }
  if (run.status === "completed" || run.status === "completed_degraded") {
    return {
      title: ui(language, "Preview version is ready"),
      detail: ui(language, "The run created a ProjectVersion. Publishing still requires an explicit user action."),
      facts: [...facts, run.version_id ? `${ui(language, "Versions")} ${run.version_id.slice(0, 8)}` : ui(language, "Version created")],
      tone: "success",
    };
  }
  if (run.status === "failed") {
    return {
      title: ui(language, "Run stopped with an error"),
      detail: conversationalText(language, run.error_message ?? latest?.payload.message, "The run failed before producing a ready preview."),
      facts: [...facts, run.error_code ?? ui(language, "Failure recorded")],
      tone: "error",
    };
  }
  return {
    title: ui(language, "Build is moving"),
    detail: latest ? eventMessage(language, latest) : ui(language, "The run has started and is waiting for the next persisted event."),
    facts,
    tone: "running",
  };
}

function BlueprintSnapshot({ blueprint, language }: { blueprint: Blueprint; language: Language }) {
  return <details className="blueprint-snapshot">
    <summary><span>{ui(language, "Blueprint")}</span><strong>{blueprint.project_name}</strong><SupportBadge level={blueprint.support_level} language={language} /></summary>
    <p>{blueprint.visual_direction}</p>
    <div className="token-row">{blueprint.pages.map((page) => <b key={page}>{page}</b>)}</div>
  </details>;
}

function BlueprintEditor({ blueprint, setBlueprint, approve, approving, language }: { blueprint: Blueprint; setBlueprint: (value: Blueprint) => void; approve: () => void; approving: boolean; language: Language }) {
  return <div className="blueprint-view">
    <div className="content-heading blueprint-heading"><RoleAvatar role="product" size="large" /><div><span>{ui(language, "Human-in-the-loop · Adapted scope")}</span><h1>{ui(language, "Confirm the scope change")}</h1><p>{ui(language, "The supported catalog can continue only after you accept the omitted requirements.")}</p></div><SupportBadge level={blueprint.support_level} language={language} /></div>
    {blueprint.support_level === "adapted" && <div className="scope-note"><CircleAlert size={17} /><div><strong>{ui(language, "Some requirements were adapted")}</strong><p>{blueprint.omitted_requirements.join(" ")}</p></div></div>}
    <div className="blueprint-form">
      <label>{ui(language, "Project name")}<input value={blueprint.project_name} onChange={(e) => setBlueprint({ ...blueprint, project_name: e.target.value })} /></label>
      <label>{ui(language, "Visual direction")}<textarea value={blueprint.visual_direction} onChange={(e) => setBlueprint({ ...blueprint, visual_direction: e.target.value })} /></label>
      <div className="blueprint-group"><span>{ui(language, "Pages")}</span><div className="token-row">{blueprint.pages.map((page) => <b key={page}>{page}</b>)}</div></div>
      <div className="blueprint-group"><span>{ui(language, "Modules")}</span><div className="token-row">{blueprint.modules.map((module) => <b key={module}>{module}</b>)}</div></div>
      <div className="blueprint-group"><span>{ui(language, "Mapped requirements")}</span><ul>{blueprint.mapped_requirements.map((item) => <li key={item}><Check size={15} /> {item}</li>)}</ul></div>
    </div>
    <div className="approval-bar"><div><strong>{ui(language, "Accept the adapted scope?")}</strong><span>{ui(language, "This records an explicit risk confirmation.")}</span></div><button onClick={approve} disabled={approving || !blueprint.project_name.trim()}>{approving ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} {ui(language, "Confirm & build")}</button></div>
  </div>;
}

function ScopeStop({ blueprint, events, run, setRun, refreshShell, setError, language }: { blueprint: Blueprint | null; events: RunEvent[]; run: RunView; setRun: (run: RunView) => void; refreshShell: () => Promise<void>; setError: (error: string) => void; language: Language }) {
  const latest = events.at(-1);
  const reason = conversationalText(language, blueprint?.support_reasons?.[0] ?? latest?.payload.message, "The team stopped before build because the request needs to be narrowed.");
  const rewrite = rewriteSuggestion(language, blueprint, events);
  // The PM draft is ready to confirm, but remains editable. needs_input is
  // terminal, so confirmation creates a fresh Run from the adapted request.
  const [revised, setRevised] = useState(rewrite);
  const [submitting, setSubmitting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const catalogDraft = isCatalogAlternative(revised);
  const submit = async () => {
    if (!revised.trim() || !catalogDraft || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const created = await api.confirmAlternative(run.run_id, revised.trim());
      setRun(created);
      await refreshShell();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Could not start the run"));
    } finally {
      setSubmitting(false);
    }
  };
  const regenerate = async () => {
    if (!revised.trim() || regenerating) return;
    setRegenerating(true);
    setError("");
    try {
      const created = await api.regenerateAlternative(run.run_id, revised.trim());
      setRun(created);
      await refreshShell();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Could not regenerate the requirement draft"));
    } finally {
      setRegenerating(false);
    }
  };
  return <div className="center-state scope-stop">
    <div className="pm-feedback-card">
      <RoleAvatar role="product" size="large" />
      <div>
        <span>{ui(language, "Product Manager feedback")}</span>
        <h1>{ui(language, "Confirm the catalog alternative")}</h1>
        <p>{ui(language, "The original product cannot be built in V1. Product Manager created a catalog alternative that keeps only its theme.")}</p>
        <p>{reason}</p>
        <small><CircleAlert size={14} /> {ui(language, "This alternative changes the product type. Accept it only if you want a catalog instead of the original application.")}</small>
      </div>
    </div>
    <div className="scope-revise">
      <label>{ui(language, "Buildable alternative")}
        <textarea value={revised} onChange={(event) => setRevised(event.target.value)} placeholder={rewrite || ui(language, "Describe a product catalog with Home, Catalog, and Product pages…")} maxLength={4000} rows={4} autoFocus />
      </label>
      {!catalogDraft && revised.trim() && <p className="scope-warning"><CircleAlert size={14} /> {ui(language, "The confirmed draft must remain a product catalog. To reinterpret a game or another product type, regenerate the requirement first.")}</p>}
      <p className="scope-hint"><Sparkles size={13} /> {ui(language, "Confirmation skips Product Manager and continues directly to architecture.")}</p>
      <div className="scope-actions">
        <button className="secondary-action" disabled={!revised.trim() || regenerating || submitting} onClick={regenerate}>{regenerating ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />} {ui(language, "Regenerate requirement draft")}</button>
        <button className="primary-action" disabled={!revised.trim() || !catalogDraft || submitting || regenerating} onClick={submit}>{submitting ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} {ui(language, "Accept alternative & build")}</button>
      </div>
      <small className="scope-regenerate-note">{ui(language, "Product Manager will reinterpret the text and return a new catalog alternative without starting a build.")}</small>
    </div>
  </div>;
}

function FailedState({ run, setRun, refreshShell, setError, language }: { run: RunView; setRun: (run: RunView) => void; refreshShell: () => Promise<void>; setError: (error: string) => void; language: Language }) {
  const [retrying, setRetrying] = useState(false);
  const failedChecks = run.validation_report?.checks.filter((check) => check.status === "fail") ?? [];
  const retry = async () => {
    if (retrying) return;
    setRetrying(true);
    setError("");
    try {
      const created = await api.createRun(run.prompt, run.mode, run.model, []);
      setRun(created);
      await refreshShell();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : ui(language, "Could not start the run"));
    } finally {
      setRetrying(false);
    }
  };
  return <div className="center-state failed-state">
    <span className="state-icon error"><X /></span>
    <h1>{ui(language, "Run stopped")}</h1>
    <p>{conversationalText(language, run.error_message, "The run failed before producing a ready preview.")}</p>
    {failedChecks.length > 0 && <div className="validation-failures">
      <strong>{ui(language, "Failed validation checks")}</strong>
      {failedChecks.map((check) => <div key={check.check_id}><CircleAlert size={14} /><span>{ui(language, check.detail || check.label)}</span></div>)}
    </div>}
    <code>{run.error_code}</code>
    <span>{ui(language, "Your project and original request are still saved.")}</span>
    <button className="primary-action" disabled={retrying || !run.prompt} onClick={retry}>{retrying ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />} {ui(language, "Retry with saved request")}</button>
    <small>{ui(language, "Retrying creates a new Run and preserves this failure record.")}</small>
  </div>;
}

function BuildingState({ run, language }: { run: RunView; language: Language }) {
  const roles: Record<string, RoleKey> = {
    team_leader: "leader",
    product_manager: "product",
    build_queue: "renderer",
    architect: "architect",
    engineer: "engineer",
    build: "renderer",
    data: "data",
    complete: "data",
  };
  const role = roles[run.current_stage] ?? "leader";
  const title = BUILDING_STAGE_TITLES[language][run.current_stage] ?? `${stageLabel(language, run.current_stage)} ${ui(language, "is working")}`;
  return <div className="center-state building-cartoon">
    <div className="working-avatar"><RoleAvatar role={role} size="hero" /></div>
    <div className="working-stage"><LoaderCircle className="spin" size={15} /><span>{stageLabel(language, run.current_stage)}</span></div>
    <h1>{title}</h1>
    <p>{ui(language, "The current stage is persisted. Refreshing this page will not lose the run.")}</p>
    <div className="build-meter"><span /></div>
  </div>;
}

function ResultWorkspace({ run, versions, setVersions, device, setDevice, tab, setTab, refreshShell, refreshRun, setError, language }: { run: RunView; versions: VersionView[]; setVersions: (v: VersionView[]) => void; device: "desktop" | "mobile"; setDevice: (v: "desktop" | "mobile") => void; tab: WorkspaceTab; setTab: (v: WorkspaceTab) => void; refreshShell: () => Promise<void>; refreshRun: (id: string) => Promise<RunView>; setError: (v: string) => void; language: Language }) {
  const current = versions.find((version) => version.id === run.version_id) ?? versions[0];
  const [title, setTitle] = useState(current?.app_spec.hero_title ?? "");
  const [body, setBody] = useState(current?.app_spec.hero_body ?? "");
  const [color, setColor] = useState(current?.app_spec.primary_color ?? "#151515");
  const [publishing, setPublishing] = useState(false);
  const [deploymentUrl, setDeploymentUrl] = useState("");
  const [previewKey, setPreviewKey] = useState(0);
  // Re-sync editable fields during render whenever the displayed version
  // changes (e.g. after Restore or Save selects a different version). This
  // avoids stale Edit-tab inputs without triggering cascading effect renders.
  const [syncedId, setSyncedId] = useState(current?.id);
  if (current && current.id !== syncedId) {
    setSyncedId(current.id);
    setTitle(current.app_spec.hero_title ?? "");
    setBody(current.app_spec.hero_body ?? "");
    setColor(current.app_spec.primary_color ?? "#151515");
    setDeploymentUrl("");
  }
  const save = async () => {
    try {
      const version = await api.revise(run.project_id, { hero_title: title, hero_body: body, primary_color: color });
      setVersions([version, ...versions]);
      await refreshRun(run.run_id);
      setPreviewKey((value) => value + 1);
      await refreshShell();
      setTab("preview");
    } catch (reason) { setError(reason instanceof Error ? reason.message : ui(language, "Save failed")); }
  };
  const publish = async () => {
    if (!current) return;
    setPublishing(true);
    try {
      const deployment = await api.publish(run.project_id, current.id, "specify_version");
      setDeploymentUrl(deployment.public_url);
      await refreshShell();
    } catch (reason) { setError(reason instanceof Error ? reason.message : ui(language, "Publish failed")); }
    finally { setPublishing(false); }
  };
  return <div className="result-view">
    <div className="result-toolbar">
      <div className="result-tabs"><button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}><Monitor size={15} /> {ui(language, "Preview")}</button><button className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}><Code2 size={15} /> {ui(language, "Edit")}</button><button className={tab === "versions" ? "active" : ""} onClick={() => setTab("versions")}><History size={15} /> {ui(language, "Versions")}</button></div>
      <div className="toolbar-actions">
        {tab === "preview" && <div className="device-switch"><button className={device === "desktop" ? "active" : ""} onClick={() => setDevice("desktop")} aria-label={ui(language, "Desktop preview")} title={ui(language, "Desktop preview")}><Monitor size={16} /></button><button className={device === "mobile" ? "active" : ""} onClick={() => setDevice("mobile")} aria-label={ui(language, "Mobile preview")} title={ui(language, "Mobile preview")}><Smartphone size={16} /></button></div>}
        <button className="publish-button" onClick={publish} disabled={publishing}>{publishing ? <LoaderCircle className="spin" size={16} /> : <Rocket size={16} />} {ui(language, "Publish")}</button>
      </div>
    </div>
    {deploymentUrl && <div className="published-banner"><Check size={16} /><span>{ui(language, "Published successfully")}</span><a href={deploymentUrl} target="_blank" rel="noreferrer">{ui(language, "Open public app")} <ExternalLink size={14} /></a></div>}
    {tab === "preview" && current && <div className="preview-stage"><div className={device === "mobile" ? "preview-frame mobile" : "preview-frame"}><iframe key={`${current.id}-${previewKey}`} src={`/preview/${current.id}`} title={ui(language, "Generated application preview")} /></div></div>}
    {tab === "edit" && <div className="edit-panel"><div className="content-heading"><div><span>{ui(language, "Structured edit")}</span><h1>{ui(language, "Refine the current version")}</h1><p>{ui(language, "Saving creates a new ProjectVersion and keeps the original.")}</p></div></div><label>{ui(language, "Hero title")}<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>{ui(language, "Hero body")}<textarea value={body} onChange={(e) => setBody(e.target.value)} /></label><label>{ui(language, "Primary color")}<div className="color-input"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /><input value={color} onChange={(e) => setColor(e.target.value)} /></div></label><button className="primary-action" onClick={save}><Check size={16} /> {ui(language, "Save as new version")}</button></div>}
    {tab === "versions" && <div className="versions-panel"><div className="content-heading"><div><span>{ui(language, "Project history")}</span><h1>{ui(language, "Versions")}</h1><p>{ui(language, "Restore always creates a new version; history is never overwritten.")}</p></div></div>{versions.map((version) => <div className="version-row" key={version.id}><span className="version-number">v{version.number}</span><div><strong>{version.summary}</strong><small>{new Date(version.created_at).toLocaleString()}</small></div>{version.id === run.version_id ? <b>{ui(language, "Current")}</b> : <button onClick={async () => { const restored = await api.restore(run.project_id, version.id); setVersions([restored, ...versions]); await refreshRun(run.run_id); }}>{ui(language, "Restore")}</button>}</div>)}</div>}
  </div>;
}

function RunLogPanel({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const label = ui(language, "Run log");
  return (
        <aside className="debug-panel workspace-run-log" aria-live="polite">
          <div className="debug-panel-head">
            <div>
              <span>{label}</span>
              <strong>{ui(language, "Run")} {run.run_id.slice(0, 8)}</strong>
            </div>
            <span className={`debug-status ${run.status}`}>{statusLabel(language, run.status)}</span>
          </div>
          <a className="download-log-button" href={api.downloadRunLog(run.run_id)} download title={ui(language, "Download log")}>
            <Download size={14} /> {ui(language, "Download log")}
          </a>
          <div className="debug-panel-meta">
            <span>{stageLabel(language, run.current_stage)}</span>
            <span>{events.length} {ui(language, events.length === 1 ? "persisted event" : "persisted events")}</span>
          </div>
          <div className="debug-stream">
            {events.length === 0 ? (
              <p className="debug-empty">{ui(language, "No persisted events yet.")}</p>
            ) : (
              [...events].reverse().map((event) => (
                <div className="debug-line" key={event.event_id}>
                  <div className="debug-line-head">
                    <b>#{event.sequence}</b>
                    <code>{eventTitle(language, event)}</code>
                    <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
                  </div>
                  <p>{eventMessage(language, event)}</p>
                </div>
              ))
            )}
          </div>
        </aside>
  );
}

function StatusPill({ status, language }: { status: string; language: Language }) { return <span className={`status-pill ${status}`}><i /> {statusLabel(language, status)}</span>; }
function ModeBadge({ mode, language }: { mode: Mode; language: Language }) { return <span className="mode-badge">{mode === "team" ? <Users size={14} /> : <Code2 size={14} />}{ui(language, mode === "team" ? "Team pipeline" : "Engineer pipeline")}</span>; }
function SupportBadge({ level, language }: { level: string; language: Language }) { return <span className={`support-badge ${level}`}>{level === "supported" ? <Check size={14} /> : <CircleAlert size={14} />}{ui(language, level)}</span>; }
