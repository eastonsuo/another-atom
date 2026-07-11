import {
  ArrowUp,
  Check,
  ChevronRight,
  CircleAlert,
  Code2,
  ExternalLink,
  History,
  Layers3,
  LoaderCircle,
  Monitor,
  Paperclip,
  Plus,
  Rocket,
  Smartphone,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { ChangeEvent, useCallback, useEffect, useState } from "react";
import { PreviewLoader } from "./components/PreviewApp";
import { TerminalPanel } from "./components/TerminalPanel";
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
    scope_review: "范围确认",
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
    scope_review: "Scope review",
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
  "Projects, repositories, versions, and Sandbox sessions stay isolated by account.": "Project、源码仓库、版本和 Sandbox Session 都按账号隔离。",
  "Display name": "显示名称",
  "Username": "用户名",
  "Password": "密码",
  "Already have an account? Sign in": "已有账号？登录",
  "Need an account? Sign up": "没有账号？注册",
  "Could not start the run": "无法启动 Run",
  "Could not open the project": "无法打开 Project",
  "Lead request sent to {model}. Waiting for model response.": "已发送给 Lead（{model}），等待模型返回。",
  "Lead routed this message to {route}.": "Lead 将消息路由到 {route}。",
  "No build run was created because Lead answered directly.": "Lead 已直接回答，没有创建构建 Run。",
  "Creating Project and Build Run.": "正在创建 Project 和构建 Run。",
  "Run created. Opening build event stream.": "Run 已创建，正在打开构建事件流。",
  "Project workspace": "Project 工作区",
  "Application studio": "应用工作台",
  "New project": "新建 Project",
  "Projects": "Projects",
  "Your generated projects will appear here.": "生成的 Project 会显示在这里。",
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
  "Submit a message to see pre-project Lead progress. Project logs appear after a Run is created.": "提交消息后会显示 Project 创建前的 Lead 进度；Run 创建后日志进入 Project。",
  "Start with an example": "从示例开始",
  "Staged pipeline": "阶段流水线",
  "Build activity": "构建活动",
  "Team pipeline": "团队流水线",
  "Engineer pipeline": "工程流水线",
  "In progress": "进行中",
  "Complete": "已完成",
  "Waiting": "等待中",
  "Project log": "Project 日志",
  "Recent events": "最近事件",
  "No persisted events yet.": "暂无持久化事件。",
  "Latest": "最新",
  "persisted event": "条持久化事件",
  "persisted events": "条持久化事件",
  "Scope needs revision": "需要调整范围",
  "The team stopped before build because the request needs to be narrowed.": "团队在构建前暂停，因为请求需要收窄。",
  "No build job was created": "未创建 Build Job",
  "Rewrite": "改写建议",
  "Waiting for approval": "等待确认",
  "The Blueprint changes the requested scope, so the build is paused until you confirm it.": "Blueprint 对请求范围做了调整，确认前不会继续构建。",
  "Blueprint ready": "Blueprint 已就绪",
  "Preview version is ready": "预览版本已就绪",
  "The run created a ProjectVersion. Publishing still requires an explicit user action.": "本次 Run 已创建 ProjectVersion；发布仍需要用户显式操作。",
  "Version created": "版本已创建",
  "Run stopped with an error": "Run 因错误停止",
  "The run failed before producing a ready preview.": "Run 在生成可预览版本前失败。",
  "Failure recorded": "失败已记录",
  "Build is moving": "构建进行中",
  "The run has started and is waiting for the next persisted event.": "Run 已启动，正在等待下一条持久化事件。",
  "Blueprint": "Blueprint",
  "Human-in-the-loop · Adapted scope": "人工确认 · 范围调整",
  "Confirm the scope change": "确认范围变化",
  "The supported catalog can continue only after you accept the omitted requirements.": "接受被省略的需求后，受支持的商品目录才能继续构建。",
  "Some requirements were adapted": "部分需求已被调整",
  "Project name": "Project 名称",
  "Visual direction": "视觉方向",
  "Pages": "页面",
  "Modules": "模块",
  "Mapped requirements": "已映射需求",
  "Accept the adapted scope?": "接受调整后的范围？",
  "This records an explicit risk confirmation.": "这会记录一次明确的风险确认。",
  "Confirm & build": "确认并构建",
  "Request needs to be narrowed": "请求需要收窄",
  "Suggested rewrite": "建议改写",
  "Run stopped": "Run 已停止",
  "Your project and original request are still saved.": "Project 和原始请求仍已保存。",
  "Build queued": "构建已排队",
  "is working": "正在工作",
  "The current stage is persisted. Refreshing this page will not lose the run.": "当前阶段已持久化，刷新页面不会丢失本次 Run。",
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
  "Saving creates a new ProjectVersion and keeps the original.": "保存会创建新的 ProjectVersion，原版本不会被覆盖。",
  "Hero title": "首屏标题",
  "Hero body": "首屏正文",
  "Primary color": "主色",
  "Save as new version": "保存为新版本",
  "Project history": "Project 历史",
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
  "needs_input": "需要补充输入",
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
    const appendActivity = (message: string, tone: ActivityEntry["tone"] = "pending") => {
      setActivityLog((current) => [...current, { id: `${Date.now()}-${current.length}`, message, tone }]);
    };
    try {
      const decision = await api.leadMessage(prompt, model, forceTeam);
      setLeadDecision(decision);
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
        <ActivityLog entries={activityLog} active={submitting} language={language} />
      </div>
      <div className="example-prompts">
        <span>{ui(language, "Start with an example")}</span>
        {EXAMPLE_PROMPTS[language].map((example, index) => <button key={example} onClick={() => setPrompt(example)}><span>0{index + 1}</span>{example}</button>)}
      </div>
    </section>
  );
}

function ActivityLog({ entries, active, language }: { entries: ActivityEntry[]; active: boolean; language: Language }) {
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
        ) : run.status === "needs_input" && blueprint ? (
          <ScopeStop blueprint={blueprint} language={language} />
        ) : run.status === "failed" ? (
          <FailedState run={run} language={language} />
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
    </div>
  );
}

function Timeline({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const requiresApproval = run.status === "awaiting_approval" || run.blueprint?.support_level === "adapted";
  const stages = run.mode === "team"
    ? ["team_leader", "product_manager", ...(requiresApproval ? ["blueprint_approval"] : []), "architect", "engineer", "build", "data", "complete"]
    : ["product_manager", ...(requiresApproval ? ["blueprint_approval"] : []), "engineer", "build", "complete"];
  const roles: Record<string, RoleKey> = { team_leader: "leader", product_manager: "product", blueprint_approval: "user", architect: "architect", engineer: "engineer", build: "renderer", data: "data", complete: "data" };
  const displayStage = run.current_stage === "build_queue" ? "engineer" : run.current_stage;
  const currentIndex = stages.indexOf(displayStage);
  return <div className="timeline">
    {stages.map((stage, index) => {
      const completed = currentIndex > index || TERMINAL.has(run.status) && run.status.startsWith("completed");
      const active = displayStage === stage;
      return <div className={active ? "timeline-item active" : completed ? "timeline-item complete" : "timeline-item"} key={stage}>
        <div className="timeline-avatar"><RoleAvatar role={roles[stage]} size="small" /><span className="timeline-state">{completed ? <Check size={10} /> : active ? <LoaderCircle className="spin" size={10} /> : index + 1}</span></div>
        <div><strong>{stageLabel(language, stage)}</strong><small>{ui(language, active ? "In progress" : completed ? "Complete" : "Waiting")}</small></div>
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
      <small>Run {run.run_id.slice(0, 8)}</small>
    </div>
    <strong>{summary.title}</strong>
    <p>{summary.detail}</p>
    <div className="project-log-facts">
      {summary.facts.map((fact) => <span key={fact}>{fact}</span>)}
    </div>
    <div className="event-log">
      <span>{ui(language, "Recent events")}</span>
      {events.length === 0 ? <p>{ui(language, "No persisted events yet.")}</p> : events.slice(-5).reverse().map((event) => <div key={event.event_id}><i /> <p>{ui(language, String(event.payload.message))}</p></div>)}
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
    return {
      title: ui(language, "Scope needs revision"),
      detail: run.blueprint?.support_reasons[0] ?? (latest?.payload.message ? ui(language, String(latest.payload.message)) : ui(language, "The team stopped before build because the request needs to be narrowed.")),
      facts: [...facts, run.blueprint?.rewrite_suggestion ? `${ui(language, "Rewrite")}: ${run.blueprint.rewrite_suggestion}` : ui(language, "No build job was created")],
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
      detail: run.error_message ?? (latest?.payload.message ? ui(language, String(latest.payload.message)) : ui(language, "The run failed before producing a ready preview.")),
      facts: [...facts, run.error_code ?? ui(language, "Failure recorded")],
      tone: "error",
    };
  }
  return {
    title: ui(language, "Build is moving"),
    detail: latest?.payload.message ? ui(language, String(latest.payload.message)) : ui(language, "The run has started and is waiting for the next persisted event."),
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

function ScopeStop({ blueprint, language }: { blueprint: Blueprint; language: Language }) {
  return <div className="center-state"><span className="state-icon warning"><CircleAlert /></span><h1>{ui(language, "Request needs to be narrowed")}</h1><p>{blueprint.support_reasons[0]}</p><div className="rewrite-box"><span>{ui(language, "Suggested rewrite")}</span><p>{blueprint.rewrite_suggestion}</p></div></div>;
}

function FailedState({ run, language }: { run: RunView; language: Language }) {
  return <div className="center-state"><span className="state-icon error"><X /></span><h1>{ui(language, "Run stopped")}</h1><p>{run.error_message}</p><code>{run.error_code}</code><span>{ui(language, "Your project and original request are still saved.")}</span></div>;
}

function BuildingState({ run, language }: { run: RunView; language: Language }) {
  const role: RoleKey = run.current_stage === "architect" ? "architect" : run.current_stage === "data" ? "data" : run.current_stage === "build" ? "renderer" : "engineer";
  return <div className="center-state building-cartoon"><div className="working-avatar"><RoleAvatar role={role} size="hero" /><span><LoaderCircle className="spin" /></span></div><h1>{run.current_stage === "build_queue" ? ui(language, "Build queued") : `${roleLabel(language, role)} ${ui(language, "is working")}`}</h1><p>{ui(language, "The current stage is persisted. Refreshing this page will not lose the run.")}</p><div className="build-meter"><span /></div></div>;
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
      <div className="result-tabs"><button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}><Monitor size={15} /> {ui(language, "Preview")}</button><button className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}><Code2 size={15} /> {ui(language, "Edit")}</button><button className={tab === "code" ? "active" : ""} onClick={() => setTab("code")}><Code2 size={15} /> {ui(language, "Vim")}</button><button className={tab === "versions" ? "active" : ""} onClick={() => setTab("versions")}><History size={15} /> {ui(language, "Versions")}</button></div>
      <div className="toolbar-actions">
        {tab === "preview" && <div className="device-switch"><button className={device === "desktop" ? "active" : ""} onClick={() => setDevice("desktop")} aria-label={ui(language, "Desktop preview")} title={ui(language, "Desktop preview")}><Monitor size={16} /></button><button className={device === "mobile" ? "active" : ""} onClick={() => setDevice("mobile")} aria-label={ui(language, "Mobile preview")} title={ui(language, "Mobile preview")}><Smartphone size={16} /></button></div>}
        <button className="publish-button" onClick={publish} disabled={publishing}>{publishing ? <LoaderCircle className="spin" size={16} /> : <Rocket size={16} />} {ui(language, "Publish")}</button>
      </div>
    </div>
    {deploymentUrl && <div className="published-banner"><Check size={16} /><span>{ui(language, "Published successfully")}</span><a href={deploymentUrl} target="_blank" rel="noreferrer">{ui(language, "Open public app")} <ExternalLink size={14} /></a></div>}
    {tab === "preview" && current && <div className="preview-stage"><div className={device === "mobile" ? "preview-frame mobile" : "preview-frame"}><iframe key={`${current.id}-${previewKey}`} src={`/preview/${current.id}`} title={ui(language, "Generated application preview")} /></div></div>}
    {tab === "edit" && <div className="edit-panel"><div className="content-heading"><div><span>{ui(language, "Structured edit")}</span><h1>{ui(language, "Refine the current version")}</h1><p>{ui(language, "Saving creates a new ProjectVersion and keeps the original.")}</p></div></div><label>{ui(language, "Hero title")}<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>{ui(language, "Hero body")}<textarea value={body} onChange={(e) => setBody(e.target.value)} /></label><label>{ui(language, "Primary color")}<div className="color-input"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /><input value={color} onChange={(e) => setColor(e.target.value)} /></div></label><button className="primary-action" onClick={save}><Check size={16} /> {ui(language, "Save as new version")}</button></div>}
    {tab === "code" && <TerminalPanel projectId={run.project_id} language={language} onError={setError} onSaved={async (version) => { setVersions([version, ...versions]); await refreshRun(run.run_id); await refreshShell(); setTab("versions"); }} />}
    {tab === "versions" && <div className="versions-panel"><div className="content-heading"><div><span>{ui(language, "Project history")}</span><h1>{ui(language, "Versions")}</h1><p>{ui(language, "Restore always creates a new version; history is never overwritten.")}</p></div></div>{versions.map((version) => <div className="version-row" key={version.id}><span className="version-number">v{version.number}</span><div><strong>{version.summary}</strong><small>{new Date(version.created_at).toLocaleString()}</small></div>{version.id === run.version_id ? <b>{ui(language, "Current")}</b> : <button onClick={async () => { const restored = await api.restore(run.project_id, version.id); setVersions([restored, ...versions]); await refreshRun(run.run_id); }}>{ui(language, "Restore")}</button>}</div>)}</div>}
  </div>;
}

function StatusPill({ status, language }: { status: string; language: Language }) { return <span className={`status-pill ${status}`}><i /> {statusLabel(language, status)}</span>; }
function ModeBadge({ mode, language }: { mode: Mode; language: Language }) { return <span className="mode-badge">{mode === "team" ? <Users size={14} /> : <Code2 size={14} />}{ui(language, mode === "team" ? "Team pipeline" : "Engineer pipeline")}</span>; }
function SupportBadge({ level, language }: { level: string; language: Language }) { return <span className={`support-badge ${level}`}>{level === "supported" ? <Check size={14} /> : <CircleAlert size={14} />}{ui(language, level)}</span>; }
