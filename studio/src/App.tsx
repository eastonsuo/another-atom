import {
  ArrowUp,
  Check,
  ChevronRight,
  CircleAlert,
  Code2,
  Download,
  ExternalLink,
  FileText,
  History,
  Layers3,
  LoaderCircle,
  LogOut,
  MessageCircle,
  Monitor,
  Paperclip,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Rocket,
  RotateCcw,
  Save,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Users,
  X,
} from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from "react";
import { PreviewLoader } from "./components/PreviewApp";
import { RepositoryPanel } from "./components/RepositoryPanel";
import { AtomLogo, ROLE_META, RoleAvatar, type RoleKey } from "./components/BrandAssets";
import { api, ApiError } from "./lib/api";
import type {
  AttachmentMeta,
  Blueprint,
  LeadDecisionView,
  Mode,
  ProjectView,
  ProjectMessageView,
  ProjectMessageResult,
  ProductSpec,
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
const SIDEBAR_COLLAPSED_KEY = "another-atom-sidebar-collapsed";

const EXAMPLE_PROMPTS: Record<Language, string[]> = {
  zh: [
    "创建一个复古像素风扫雷游戏，包含 9×9 棋盘、10 个地雷、计时、插旗、胜负提示和重新开始。",
    "创建一个个人任务看板，可以添加任务、切换状态、按优先级筛选，并在浏览器本地保存演示状态。",
  ],
  en: [
    "Build a retro pixel-style Minesweeper game with a 9×9 board, 10 mines, flags, timer, win/loss feedback, and restart.",
    "Create a personal task board with task creation, status changes, priority filters, and local browser demo state.",
  ],
};

const STAGE_LABELS: Record<Language, Record<string, string>> = {
  zh: {
    team_leader: "团队负责人",
    product_manager: "产品经理",
    product_manager_clarification: "产品经理澄清",
    blueprint_approval: "用户确认",
    architect: "架构师",
    engineer: "工程师",
    data: "数据分析师",
    build: "校验器",
    reviewer: "审查员",
    complete: "预览就绪",
    build_queue: "构建队列",
    scope_review: "确认 PM 草案",
  },
  en: {
    team_leader: "AI Lead",
    product_manager: "Product Manager",
    product_manager_clarification: "PM clarification",
    blueprint_approval: "Your approval",
    architect: "Architect",
    engineer: "Engineer",
    data: "Data Analyst",
    build: "Validator",
    reviewer: "Reviewer",
    complete: "Preview ready",
    build_queue: "Build queue",
    scope_review: "Confirm PM draft",
  },
};

const BUILDING_STAGE_TITLES: Record<Language, Record<string, string>> = {
  zh: {
    team_leader: "团队负责人正在判断如何处理请求",
    product_manager: "产品经理正在整理需求",
    product_manager_clarification: "产品经理正在等待你补充需求",
    build_queue: "构建任务正在排队",
    architect: "架构师正在设计方案",
    engineer: "工程师正在生成应用规格",
    data: "数据分析师正在分析应用数据",
    build: "校验器正在检查源码与交付证据",
    reviewer: "审查员正在独立审查结果",
    complete: "正在准备预览结果",
  },
  en: {
    team_leader: "AI Lead is routing the request",
    product_manager: "Product Manager is structuring the requirement",
    product_manager_clarification: "Product Manager is waiting for your clarification",
    build_queue: "The build job is waiting to start",
    architect: "Architect is designing the solution",
    engineer: "Engineer is generating the application specification",
    data: "Data Analyst is analyzing application data",
    build: "Validator is checking source and delivery evidence",
    reviewer: "Reviewer is independently checking the result",
    complete: "Preparing the preview result",
  },
};

const ROLE_LABELS: Record<Language, Partial<Record<RoleKey, string>>> = {
  zh: {
    leader: "团队负责人",
    product: "产品",
    architect: "架构",
    engineer: "工程",
    data: "数据",
    reviewer: "审查",
    validator: "校验",
    renderer: "渲染",
    user: "你",
  },
  en: {
    leader: "AI Lead",
  },
};

const ZH: Record<string, string> = {
  "Authentication failed": "登录失败",
  "Username must be 3–80 characters and use only letters, numbers, _ or -.": "用户名需为 3–80 个字符，只能包含字母、数字、下划线或连字符。",
  "Password must be at least 10 characters.": "密码至少需要 10 个字符。",
  "Username or password is incorrect": "用户名或密码不正确。",
  "That username is already in use": "该用户名已被使用。",
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
  "AI Lead request sent to {model}. Waiting for model response.": "已发送给团队负责人（{model}），等待模型返回。",
  "AI Lead is deciding whether to answer, clarify, or call the team": "团队负责人正在判断直接回答、结构化澄清还是调用团队",
  "Project and Run logs start after this step completes.": "此步骤完成后才会创建 Project，并接入 Run 日志。",
  "Model response is slower than usual.": "模型响应比平时慢，仍在等待服务端返回。",
  "Ollama timed out. Switching provider to DeepSeek official API…": "Ollama 响应超时，服务商切换中：DeepSeek 官方 API……",
  "Provider fallback completed: {provider}.": "服务商切换完成：{provider}。",
  "seconds": "秒",
  "AI Lead routed this message to {route}.": "团队负责人选择了{route}。",
  "No build run was created because AI Lead answered directly.": "团队负责人已直接回答，没有创建构建任务。",
  "AI Lead is waiting for structured clarification. No build run was created.": "团队负责人正在等待结构化补充，没有创建构建任务。",
  "Creating Project and Build Run.": "正在创建项目和构建任务。",
  "Run created. Opening build event stream.": "任务已创建，正在打开构建事件流。",
  "Project workspace": "项目工作区",
  "Application studio": "应用工作台",
  "New project": "新建项目",
  "Collapse project sidebar": "收起项目栏",
  "Expand project sidebar": "展开项目栏",
  "Projects": "项目",
  "Your generated projects will appear here.": "生成的项目会显示在这里。",
  "Model calls": "模型调用",
  "LLM calls are isolated to this account.": "每次实际模型请求计 1 次，按当前账号隔离。",
  "Sign out": "退出登录",
  "Admin console": "管理后台",
  "Real LLM is active": "真实 LLM 已启用",
  "Mock LLM is active": "Mock LLM 已启用",
  "Your build team": "你的构建团队",
  "Talk to the AI team": "和 AI 团队沟通",
  "Ask a question, clarify the scope, or explicitly request a Web application build.": "可以询问、澄清范围，或明确要求构建任意 Web 应用。",
  "Describe the application, behavior, interactions, and visual direction…": "描述你想实现的应用、功能、交互和视觉方向……",
  "Add reference attachments": "添加参考附件",
  "Language model": "语言模型",
  "Send message": "发送消息",
  "Remove attachment": "移除附件",
  "Call team": "调用团队",
  "Not sure yet": "暂不确定",
  "Next": "下一步",
  "choices completed": "项已完成",
  "Request routing": "任务判断",
  "Submit a message to see how it is handled. Project logs appear after a Run is created.": "提交消息后会先判断直接回答还是调用团队；任务创建后日志进入项目。",
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
  "The team stopped before build because the request needs to be narrowed.": "当前需求包含 Web Runtime 无法直接提供的能力，需要确认调整后再构建。",
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
  "Engineer is repairing the failed validation checks": "工程师正在根据校验结果修复生成代码。",
  "Engineer produced one revised AppSpec": "工程师已生成一次修订后的应用方案。",
  "The revised AppSpec completed deterministic validation": "修订后的应用方案已完成重新校验。",
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
  "The Web application can continue after you accept the adapted runtime capabilities.": "接受被调整或省略的运行能力后，Web 应用才能继续构建。",
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
  "Product Manager expanded the original goal into a buildable Web requirement.": "产品经理保留了原始产品目标，并补全为可构建的 Web 需求。",
  "Confirm the requirement draft": "确认 PM 生成的需求草案",
  "Review the behavior, interactions, states, and visual direction before building.": "请检查功能、交互、状态和视觉方向；确认后再开始构建。",
  "Requirement draft": "需求草案",
  "Confirm requirement & build": "确认需求并开始构建",
  "Regenerate requirement draft": "让 PM 重新生成需求草案",
  "Product Manager will reinterpret the text and return a new requirement draft without starting a build.": "产品经理会重新理解输入并生成新的需求草案，不会开始构建。",
  "Could not regenerate the requirement draft": "无法重新生成需求草案",
  "Confirmation skips Product Manager and continues directly to architecture.": "确认后不会再次调用产品经理，将直接进入架构阶段。",
  "Describe the product behavior, interactions, states, and visual direction…": "描述产品功能、交互、状态和视觉方向……",
  "Run stopped": "任务已停止",
  "Your project and original request are still saved.": "项目和原始请求仍已保存。",
  "Build queued": "构建已排队",
  "is working": "正在工作",
  "The current stage is persisted. Refreshing this page will not lose the run.": "当前阶段已持久化，刷新页面不会丢失本次任务。",
  "Save failed": "保存失败",
  "Publish failed": "发布失败",
  "Preview": "预览",
  "Edit": "编辑",
  "Project conversation": "项目对话",
  "Describe what should change in the current version.": "描述你希望基于当前版本修改什么。",
  "Ask about the Project or describe what you want to change.": "询问项目，或描述你想修改的内容。",
  "Could not load Project messages": "无法读取 Project 对话",
  "Could not start Project change": "无法开始 Project 修改",
  "This clarification expired because the Project changed. Send the change again from the current version.": "等待澄清期间 Project 已产生新版本。请基于当前版本重新发送修改要求。",
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
  "clarify": "等待结构化补充",
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
  "review_running": "审查阶段",
  "Product Manager is structuring the request": "产品经理正在整理需求",
  "Blueprint is ready for review": "Blueprint 已生成，等待检查",
  "The request is outside the V1 catalog scope": "当前需求包含旧版商品目录范围之外的能力，请让 PM 按原始目标重新生成 Web 需求。",
  "V1 only supports product catalog sites (Home, Catalog, Product pages), not interactive games.": "这是一条旧版本范围说明；当前版本已经支持生成自包含 Web 交互应用。",
  "Describe a product showcase or catalog with Home, Catalog, and Product pages.": "请描述原始产品目标、功能、交互、状态和视觉方向。",
  "To use V1, consider creating a product catalog for a board game store, featuring minesweeper-themed products, with Home, Catalog, and Product pages.": "请让 PM 围绕扫雷游戏本身重新生成需求，不要改成商品目录。",
  "Review and confirm the Blueprint before building": "构建前需要检查并确认 Blueprint",
  "Supported Blueprint is within the requested scope and base budget": "受支持 Blueprint 在请求范围和基础预算内",
  "Build is queued": "构建已进入队列",
  "Architect is defining structure, data boundaries, and visual tokens": "架构师正在定义结构、数据边界和视觉 Token",
  "ArchitectureSpec passed schema validation": "ArchitectureSpec 已通过结构校验",
  "Engineer is producing the renderer contract": "工程师正在生成渲染器 Contract",
  "Engineer is generating the Web source contract": "工程师正在生成 HTML、CSS 和 JavaScript",
  "AppSpec passed schema validation": "AppSpec 已通过结构校验",
  "Controlled React renderer started": "受控 React 渲染器已启动",
  "Web source packaging and sandbox validation started": "Web 源码正在物化并进行 Sandbox 边界校验",
  "Deterministic route, data, and renderer checks completed": "路由、数据和渲染器确定性校验已完成",
  "Deterministic source, capability, handoff, and visual checks completed": "源码、能力边界、角色交接和视觉校验已完成",
  "Data Analyst is analyzing application data and local state": "数据分析师正在分析应用数据和本地状态",
  "DataProfile is ready": "DataProfile 已生成",
  "Reviewer is checking requirement coverage and immutable evidence": "审查员正在检查需求覆盖和不可变证据",
  "ReviewReport is ready": "ReviewReport 已生成",
  "Interactive preview is ready": "可交互预览已就绪",
  "The build worker stopped unexpectedly": "Build Worker 异常停止",
  "event.run.created": "任务已创建",
  "event.stage.started": "阶段已开始",
  "event.engineer.context.prepared": "工程上下文已准备",
  "event.engineer.repair_context.prepared": "修复上下文已准备",
  "event.agent.attempt.started": "模型请求已开始",
  "event.agent.output.validated": "模型输出已通过 Contract 校验",
  "event.agent.retry": "模型请求失败",
  "event.artifact.created": "产物已保存",
  "event.approval.required": "等待确认",
  "event.run.needs_input": "需要补充输入",
  "event.run.completed": "任务已完成",
  "event.run.failed": "任务失败",
  "event.provider.fallback": "服务商已切换",
  "event.alternative.regeneration_requested": "PM 草案重新生成",
  "event.product_spec.updated": "产品说明摘要已更新",
  "event.product_spec.regenerated": "产品说明已重新生成",
  "Product specification summary was updated": "产品说明摘要已更新",
  "Product specification was regenerated from the current draft": "产品说明已基于当前内容重新生成",
  "A new requirement draft is queued for Product Manager": "已请求产品经理重新生成需求草案",
  "User asked Product Manager to regenerate the requirement draft": "用户已要求产品经理重新生成需求草案",
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
  const attempt = typeof event.payload.attempt === "number" ? event.payload.attempt : null;
  const maxAttempts = typeof event.payload.max_attempts === "number" ? event.payload.max_attempts : null;
  if (event.type === "agent.attempt.started" && attempt && maxAttempts) {
    return language === "zh"
      ? `第 ${attempt} 次模型请求已发出（最多尝试 ${maxAttempts} 次），正在生成本阶段结果。`
      : `Model request ${attempt} was sent (up to ${maxAttempts} attempts); waiting for this stage's result.`;
  }
  if (event.type === "agent.output.validated" && attempt && maxAttempts) {
    return language === "zh"
      ? `第 ${attempt}/${maxAttempts} 次模型输出已完成解析并通过 Contract 校验。`
      : `Model attempt ${attempt}/${maxAttempts} was parsed and passed Contract validation.`;
  }
  if (event.type === "agent.retry" && attempt && maxAttempts) {
    const failureKind = typeof event.payload.failure_kind === "string" ? event.payload.failure_kind : "provider_error";
    const labels: Record<string, [string, string]> = {
      provider_timeout: ["模型服务超时", "provider timeout"],
      provider_configuration: ["模型服务配置错误", "provider configuration error"],
      contract_validation: ["结构化输出未通过 Contract 校验", "structured output failed Contract validation"],
      provider_response: ["模型响应为空或格式异常", "provider response was empty or malformed"],
      provider_error: ["模型服务请求或响应处理失败", "provider request or response handling failed"],
    };
    const reason = labels[failureKind]?.[language === "zh" ? 0 : 1] ?? failureKind;
    const willRetry = event.payload.will_retry === true;
    return language === "zh"
      ? `第 ${attempt}/${maxAttempts} 次请求失败：${reason}。${willRetry ? "正在准备下一次尝试。" : "重试次数已用完。"}`
      : `Attempt ${attempt}/${maxAttempts} failed: ${reason}. ${willRetry ? "Preparing the next attempt." : "The retry budget is exhausted."}`;
  }
  return displayText(language, event.payload.message ?? event.type) || eventTitle(language, event);
}

function eventTimestampMs(timestamp: string): number | null {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp);
  const parsed = Date.parse(hasTimezone ? timestamp : `${timestamp}Z`);
  return Number.isFinite(parsed) ? parsed : null;
}

function rewriteSuggestion(language: Language, blueprint: Blueprint | null, events: RunEvent[]): string {
  const latestRewrite = [...events].reverse().find((event) => typeof event.payload.rewrite_suggestion === "string")?.payload.rewrite_suggestion;
  return conversationalText(language, blueprint?.rewrite_suggestion ?? latestRewrite, "Describe the product behavior, interactions, states, and visual direction…");
}

function LanguageToggle({
  language,
  setLanguage,
}: {
  language: Language;
  setLanguage: (language: Language) => void;
}) {
  return <div className="language-toggle" aria-label={language === "zh" ? "语言切换" : "Language switch"}>
    <button type="button" className={language === "zh" ? "active" : ""} onClick={() => setLanguage("zh")}>中文</button>
    <button type="button" className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
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
  const usernameValidationError = username.length > 0 && !/^[a-zA-Z0-9_-]{3,80}$/.test(username.trim())
    ? ui(language, "Username must be 3–80 characters and use only letters, numbers, _ or -.")
    : "";
  const passwordValidationError = password.length > 0 && password.length < 10
    ? ui(language, "Password must be at least 10 characters.")
    : "";
  const visibleError = error || usernameValidationError || passwordValidationError;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedUsername = username.trim();
    if (!/^[a-zA-Z0-9_-]{3,80}$/.test(normalizedUsername)) {
      setError(ui(language, "Username must be 3–80 characters and use only letters, numbers, _ or -."));
      return;
    }
    if (password.length < 10) {
      setError(ui(language, "Password must be at least 10 characters."));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      onAuthenticated(signup
        ? await api.signup(normalizedUsername, password, displayName)
        : await api.login(normalizedUsername, password));
    } catch (reason) {
      setError(reason instanceof Error ? ui(language, reason.message) : ui(language, "Authentication failed"));
    } finally {
      setSubmitting(false);
    }
  };
  return <main className="auth-view">
    <form className="auth-card" onSubmit={submit} noValidate>
      <div className="auth-head"><div className="brand"><AtomLogo /><strong>Another Atom</strong></div><LanguageToggle language={language} setLanguage={setLanguage} /></div>
      <span>{ui(language, signup ? "Create account" : "Session Gateway")}</span>
      <h1>{ui(language, signup ? "Create your workspace" : "Sign in")}</h1>
      <p>{ui(language, "Projects, repositories, versions, and Sandbox sessions stay isolated by account.")}</p>
      {signup && <label>{ui(language, "Display name")}<input value={displayName} onChange={(event) => { setDisplayName(event.target.value); setError(""); }} autoComplete="name" /></label>}
      <label>{ui(language, "Username")}<input value={username} onChange={(event) => { setUsername(event.target.value); setError(""); }} autoComplete="username" aria-invalid={Boolean(usernameValidationError)} aria-describedby={visibleError ? "auth-error" : undefined} /></label>
      <label>{ui(language, "Password")}<input type="password" value={password} onChange={(event) => { setPassword(event.target.value); setError(""); }} autoComplete={signup ? "new-password" : "current-password"} aria-invalid={Boolean(passwordValidationError)} aria-describedby={visibleError ? "auth-error" : undefined} /></label>
      {visibleError && <div id="auth-error" className="inline-error auth-error" role="alert" aria-live="assertive"><CircleAlert size={16} /> <span>{visibleError}</span></div>}
      <button type="submit" className="primary-action" disabled={submitting}>{submitting && <LoaderCircle className="spin" size={16} />}{ui(language, signup ? "Create account" : "Sign in")}</button>
      <button type="button" className="auth-switch" onClick={() => { setSignup((value) => !value); setError(""); }}>{ui(language, signup ? "Already have an account? Sign in" : "Need an account? Sign up")}</button>
    </form>
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true");

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    window.localStorage.setItem(LANGUAGE_KEY, nextLanguage);
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((current) => {
      const next = !current;
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
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
      "engineer.context.prepared",
      "engineer.repair_context.prepared",
      "agent.attempt.started",
      "agent.output.validated",
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

  const sendToLead = async (forceTeam = false, messageOverride?: string) => {
    const effectivePrompt = messageOverride?.trim() || prompt.trim();
    if (!effectivePrompt || submitting) return;
    setSubmitting(true);
    setError("");
    setActivityLog([
      {
        id: `${Date.now()}-lead-started`,
        message: template(language, "AI Lead request sent to {model}. Waiting for model response.", { model }),
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
      const decision = await api.leadMessage(effectivePrompt, model, forceTeam);
      window.clearInterval(leadTimer);
      setLeadDecision(decision);
      if (decision.fallback_provider) {
        appendActivity(template(language, "Provider fallback completed: {provider}.", { provider: decision.fallback_provider }), "success");
      }
      appendActivity(template(language, "AI Lead routed this message to {route}.", { route: routeLabel(language, decision.route) }), "success");
      if (decision.route !== "team") {
        appendActivity(
          ui(
            language,
            decision.route === "clarify"
              ? "AI Lead is waiting for structured clarification. No build run was created."
              : "No build run was created because AI Lead answered directly.",
          ),
          "success",
        );
        await refreshShell();
        return;
      }
      appendActivity(ui(language, "Creating Project and Build Run."), "pending");
      const created = await api.createRun(effectivePrompt, "team", model, attachments);
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
    <div className={sidebarCollapsed ? "studio-shell sidebar-collapsed" : "studio-shell"}>
      <Sidebar
        projects={projects}
        quota={quota}
        activeProjectId={run?.project_id}
        user={user}
        language={language}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
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
  collapsed,
  onToggle,
  onNew,
  onOpen,
  onLogout,
}: {
  projects: ProjectView[];
  quota: QuotaView | null;
  activeProjectId?: string;
  user: UserView;
  language: Language;
  collapsed: boolean;
  onToggle: () => void;
  onNew: () => void;
  onOpen: (project: ProjectView) => void;
  onLogout: () => void;
}) {
  return (
    <aside className={collapsed ? "studio-sidebar collapsed" : "studio-sidebar"}>
      <div className="sidebar-header">
        {!collapsed && <div className="brand"><AtomLogo /><strong>Another Atom</strong></div>}
        <button className="sidebar-toggle" onClick={onToggle} aria-label={ui(language, collapsed ? "Expand project sidebar" : "Collapse project sidebar")} title={ui(language, collapsed ? "Expand project sidebar" : "Collapse project sidebar")} aria-expanded={!collapsed}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
      </div>
      <button className="new-project" onClick={onNew} title={ui(language, "New project")}><Plus size={17} /> <span>{ui(language, "New project")}</span></button>
      <div className="sidebar-section">
        <span className="sidebar-label">{ui(language, "Projects")}</span>
        <div className="project-list">
          {projects.length === 0 && <p className="sidebar-empty">{ui(language, "Your generated projects will appear here.")}</p>}
          {projects.map((project) => (
            <button
              key={project.id}
              className={project.id === activeProjectId ? "project-link active" : "project-link"}
              onClick={() => onOpen(project)}
              title={project.name}
            >
              <span className="project-icon"><Layers3 size={15} /></span>
              <span><strong>{project.name}</strong><small>{statusLabel(language, project.status)}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      </div>
      <div className="quota-panel">
        <div>
          <span>{ui(language, "Model calls")}</span>
          <strong>{quota ? (language === "zh" ? `已调用 ${quota.used} 次` : `${quota.used} calls`) : "–"}</strong>
        </div>
        <small>{ui(language, "LLM calls are isolated to this account.")}</small>
      </div>
      {user.role === "admin" && <a className="admin-console-link" href="/admin"><ShieldCheck size={16} /><span>{ui(language, "Admin console")}</span><ChevronRight size={15} /></a>}
      <button className="account-button" onClick={onLogout} title={ui(language, "Sign out")}><LogOut size={16} /><span><b>{user.display_name}</b><small>{ui(language, "Sign out")}</small></span></button>
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
  sendToLead: (forceTeam?: boolean, messageOverride?: string) => void;
}) {
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  useEffect(() => {
    setClarificationAnswers({});
  }, [leadDecision?.message_id]);
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
          {(["leader", "product", "architect", "engineer", "data", "reviewer"] as RoleKey[]).map((role) => (
            <div className="crew-member" key={role}>
              <RoleAvatar role={role} size="large" />
              <span>{roleLabel(language, role)}</span>
            </div>
          ))}
        </div>
        <h1>{ui(language, "Talk to the AI team")}</h1>
        <p>{ui(language, "Ask a question, clarify the scope, or explicitly request a Web application build.")}</p>
      </div>
      <div className="composer-layout">
        <div className="composer-primary">
          <div className="composer-box">
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={ui(language, "Describe the application, behavior, interactions, and visual direction…")}
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
              <button className="submit-prompt" disabled={!prompt.trim() || !model || submitting} onClick={() => sendToLead()} aria-label={ui(language, "Send message")} title={ui(language, "Send message")}>
                {submitting ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={19} />}
              </button>
            </div>
          </div>
          {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
          {leadDecision?.route === "direct" && <div className="lead-reply"><RoleAvatar role="leader" size="small" /><div><strong>{roleLabel(language, "leader")}</strong><p>{leadDecision.response}</p><small>{leadDecision.reason}</small></div><button onClick={() => sendToLead(true)}>{ui(language, "Call team")}</button></div>}
          {leadDecision?.route === "clarify" && (() => {
            const questions = leadDecision.clarification_questions;
            const completed = questions.filter((question) => clarificationAnswers[question.id]).length;
            const ready = questions.length > 0 && completed === questions.length;
            const continueToTeam = () => {
              if (!ready) return;
              const answerLines = questions.map((question) => {
                const selectedValue = clarificationAnswers[question.id];
                const selected = question.options.find((option) => option.value === selectedValue);
                const label = selectedValue === "__unsure__" ? ui(language, "Not sure yet") : selected?.label ?? selectedValue;
                return `- ${question.question}：${label}`;
              });
              const heading = language === "zh" ? "用户结构化补充：" : "Structured user clarification:";
              void sendToLead(true, `${prompt.trim()}\n\n${heading}\n${answerLines.join("\n")}`);
            };
            return <div className="lead-clarification-card">
              <div className="lead-clarification-head"><RoleAvatar role="leader" size="small" /><div><strong>{roleLabel(language, "leader")}</strong><p>{leadDecision.response}</p><small>{leadDecision.reason}</small></div></div>
              <div className="lead-clarification-questions">
                {questions.map((question, index) => <fieldset key={question.id}>
                  <legend><span>{index + 1}</span>{question.question}</legend>
                  <div className="lead-clarification-options">
                    {[...question.options, { value: "__unsure__", label: ui(language, "Not sure yet"), description: null }].map((option) => <button
                      type="button"
                      className={clarificationAnswers[question.id] === option.value ? "selected" : ""}
                      aria-pressed={clarificationAnswers[question.id] === option.value}
                      onClick={() => setClarificationAnswers((current) => ({ ...current, [question.id]: option.value }))}
                      key={option.value}
                    ><strong>{option.label}</strong>{option.description && <small>{option.description}</small>}</button>)}
                  </div>
                </fieldset>)}
              </div>
              <div className="lead-clarification-footer"><span>{completed} / {questions.length} {ui(language, "choices completed")}</span><button type="button" disabled={!ready || submitting} onClick={continueToTeam}>{submitting ? <LoaderCircle className="spin" size={15} /> : <ArrowUp size={15} />}{ui(language, "Next")}</button></div>
            </div>;
          })()}
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
      <span>{ui(language, "Request routing")}</span>
      {active && <LoaderCircle className="spin" size={14} />}
    </div>
    {entries.length === 0 ? (
      <p className="activity-empty">{ui(language, "Submit a message to see how it is handled. Project logs appear after a Run is created.")}</p>
    ) : (
      <div className="activity-list">
        {entries.map((entry) => <div className={`activity-item ${entry.tone}`} key={entry.id}><i /> <p>{entry.message}</p></div>)}
      </div>
    )}
    {active && <div className="lead-wait-log">
      <div><LoaderCircle className="spin" size={14} /><strong>{ui(language, "AI Lead is deciding whether to answer, clarify, or call the team")}</strong><time>{elapsed} {ui(language, "seconds")}</time></div>
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
  const [requestedFilePath, setRequestedFilePath] = useState<string | null>(null);
  const effectiveBlueprint = run.blueprint;
  const ready = run.status === "completed" || run.status === "completed_degraded";

  const approve = async () => {
    if (!effectiveBlueprint) return;
    setApproving(true);
    setError("");
    try {
      const queued = await api.approve(run.run_id, effectiveBlueprint);
      setRun(queued);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  };

  const updateProductSpec = async (summary: string, action: "save" | "regenerate") => {
    setError("");
    try {
      const updated = await api.updateProductSpec(run.run_id, summary, action);
      setRun(updated);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Product specification update failed";
      setError(message);
      throw reason;
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
        {run.status === "awaiting_approval" && effectiveBlueprint ? (
          <ProductSpecApproval key={`${run.product_spec?.content_hash}:${run.product_spec?.summary}`} productSpec={run.product_spec} blueprint={effectiveBlueprint} approve={approve} approving={approving} language={language} onOpenDocument={() => setRequestedFilePath(run.product_spec?.path ?? "docs/product-spec.md")} onUpdate={updateProductSpec} />
        ) : run.status === "needs_input" && run.pending_human_task?.kind === "input_request" ? (
          <div className="failed-project-view">
            <ClarificationState run={run} language={language} />
            <ProjectChatPanel run={run} refreshShell={refreshShell} refreshRun={refreshRun} setError={setError} language={language} />
          </div>
        ) : run.status === "needs_input" ? (
          <ScopeStop blueprint={effectiveBlueprint} events={events} run={run} setRun={setRun} refreshShell={refreshShell} setError={setError} language={language} />
        ) : run.status === "failed" ? (
          <div className="failed-project-view">
            <FailedState run={run} setRun={setRun} refreshShell={refreshShell} setError={setError} language={language} />
            <ProjectChatPanel run={run} refreshShell={refreshShell} refreshRun={refreshRun} setError={setError} language={language} />
          </div>
        ) : run.status === "cancelled" && run.error_code === "BASE_VERSION_CHANGED" ? (
          <div className="failed-project-view">
            <StaleClarificationState language={language} />
            <ProjectChatPanel run={run} refreshShell={refreshShell} refreshRun={refreshRun} setError={setError} language={language} />
          </div>
        ) : ready && (run.version_id || versions.length > 0) ? (
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
          <div className="failed-project-view">
            <BuildingState run={run} events={events} language={language} />
            {versions.length > 0 && <ProjectChatPanel run={run} refreshShell={refreshShell} refreshRun={refreshRun} setError={setError} language={language} />}
          </div>
        )}
      </section>
      <RepositoryPanel run={run} events={events} language={language} sandboxAvailable={sandboxAvailable} logPanel={<RunLogPanel run={run} events={events} language={language} />} requestedFilePath={requestedFilePath} onRequestedFileOpened={() => setRequestedFilePath(null)} onError={setError} onVersionSaved={async (version) => { setVersions([version, ...versions]); await refreshRun(run.run_id); await refreshShell(); }} />
    </div>
  );
}

function Timeline({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const stages = run.mode === "team"
    ? ["team_leader", "product_manager", "architect", "engineer", "data", "reviewer", "complete"]
    : ["product_manager", "engineer", "complete"];
  const flow = run.mode === "team"
    ? ["team_leader", "product_manager", "product_manager_clarification", "scope_review", "blueprint_approval", "build_queue", "architect", "engineer", "data", "build", "reviewer", "complete"]
    : ["product_manager", "product_manager_clarification", "scope_review", "blueprint_approval", "build_queue", "engineer", "build", "complete"];
  const roles: Record<string, RoleKey> = { team_leader: "leader", product_manager: "product", architect: "architect", engineer: "engineer", data: "data", reviewer: "reviewer", complete: "reviewer" };
  const currentIndex = flow.indexOf(run.current_stage);
  const runComplete = run.status === "completed" || run.status === "completed_degraded";
  return <div className="timeline">
    {stages.map((stage) => {
      const stageIndex = flow.indexOf(stage);
      const completed = runComplete || currentIndex > stageIndex;
      const active = !runComplete && run.current_stage === stage;
      const state = active ? "In progress" : completed ? "Complete" : "Waiting";
      return <div className={active ? "timeline-item active" : completed ? "timeline-item complete" : "timeline-item"} key={stage}>
        <div className="timeline-avatar"><RoleAvatar role={roles[stage]} size="small" /><span className="timeline-state">{completed ? <Check size={10} /> : active ? <LoaderCircle className="spin" size={10} /> : stages.indexOf(stage) + 1}</span></div>
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
    <div className="project-log-current">
      <span>{stageLabel(language, run.current_stage)}</span>
      <span>{latest ? eventTitle(language, latest) : ui(language, "No persisted events yet.")}</span>
      {latest && <time>{new Date(latest.timestamp).toLocaleTimeString()}</time>}
    </div>
  </div>;
}

function summarizeProjectLog(run: RunView, events: RunEvent[], language: Language): { title: string; detail: string; tone: "running" | "success" | "warning" | "error" } {
  const latest = events.at(-1);
  if (run.status === "needs_input") {
    const clarification = run.pending_human_task?.kind === "input_request";
    const reason = clarification
      ? run.pending_human_task?.prompt ?? "Product Manager needs more information."
      : conversationalText(language, run.blueprint?.support_reasons[0] ?? latest?.payload.message, "The team stopped before build because the request needs to be narrowed.");
    return {
      title: clarification ? (language === "zh" ? "等待你补充需求" : "Waiting for your clarification") : ui(language, "Scope needs revision"),
      detail: reason,
      tone: "warning",
    };
  }
  if (run.status === "awaiting_approval") {
    return {
      title: ui(language, "Waiting for approval"),
      detail: ui(language, "The Blueprint changes the requested scope, so the build is paused until you confirm it."),
      tone: "warning",
    };
  }
  if (run.status === "completed" || run.status === "completed_degraded") {
    return {
      title: ui(language, "Preview version is ready"),
      detail: ui(language, "The run created a ProjectVersion. Publishing still requires an explicit user action."),
      tone: "success",
    };
  }
  if (run.status === "failed") {
    return {
      title: ui(language, "Run stopped with an error"),
      detail: conversationalText(language, run.error_message ?? latest?.payload.message, "The run failed before producing a ready preview."),
      tone: "error",
    };
  }
  return {
    title: ui(language, "Build is moving"),
    detail: latest ? eventMessage(language, latest) : ui(language, "The run has started and is waiting for the next persisted event."),
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

function ProductSpecApproval({ productSpec, blueprint, approve, approving, language, onOpenDocument, onUpdate }: { productSpec: ProductSpec | null; blueprint: Blueprint; approve: () => void; approving: boolean; language: Language; onOpenDocument: () => void; onUpdate: (summary: string, action: "save" | "regenerate") => Promise<void> }) {
  const chinese = language === "zh";
  const [summary, setSummary] = useState(productSpec?.summary ?? "");
  const [updating, setUpdating] = useState<"save" | "regenerate" | null>(null);
  const summaryDirty = Boolean(productSpec && summary.trim() !== productSpec.summary);
  const update = async (action: "save" | "regenerate") => {
    if (!summary.trim() || updating) return;
    setUpdating(action);
    try { await onUpdate(summary.trim(), action); }
    finally { setUpdating(null); }
  };
  return <div className="blueprint-view product-spec-approval">
    <div className="content-heading blueprint-heading"><RoleAvatar role="product" size="large" /><div><span>{chinese ? "产品经理 · 产品方案" : "Product Manager · Product plan"}</span><h1>{chinese ? "产品说明待确认" : "Product specification ready"}</h1><p>{chinese ? "产品经理已把需求整理成 Markdown 文档。这里不展示视觉稿，请先查看完整产品说明。" : "The Product Manager prepared a Markdown specification. Review the document before continuing."}</p></div><SupportBadge level={blueprint.support_level} language={language} /></div>
    {blueprint.support_level === "adapted" && <div className="scope-note"><CircleAlert size={17} /><div><strong>{chinese ? "方案包含能力调整" : "The plan includes capability adaptations"}</strong><p>{chinese ? `共 ${blueprint.omitted_requirements.length} 项调整，具体内容和验收边界已写入产品说明。` : `${blueprint.omitted_requirements.length} adaptations are documented with their acceptance boundaries.`}</p></div></div>}
    <div className="product-spec-card">
      <FileText size={24} />
      <div className="product-spec-card-body">
        <span>{chinese ? "方案摘要" : "Plan summary"}</span>
        {productSpec ? <textarea className="product-spec-summary-editor" value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={600} aria-label={chinese ? "方案摘要" : "Plan summary"} /> : <p>{chinese ? "当前任务由旧版本创建，尚无独立产品说明文件。" : "This legacy run does not have a standalone product specification file."}</p>}
        {productSpec && <div className="product-spec-summary-actions"><small>{summaryDirty ? (chinese ? "摘要已修改，保存或重新生成后才能确认。" : "Save or regenerate the changed summary before approval.") : (chinese ? "可以直接修改，也可以基于当前内容重新生成。" : "Edit directly or regenerate from the current draft.")}</small><span><button type="button" onClick={() => void update("save")} disabled={!summaryDirty || Boolean(updating)}>{updating === "save" ? <LoaderCircle className="spin" size={14} /> : <Save size={14} />}{chinese ? "保存修改" : "Save"}</button><button type="button" onClick={() => void update("regenerate")} disabled={!summary.trim() || Boolean(updating)}>{updating === "regenerate" ? <LoaderCircle className="spin" size={14} /> : <RotateCcw size={14} />}{chinese ? "基于当前内容重新生成" : "Regenerate from current"}</button></span></div>}
        <div className="product-spec-document">
          <div><span>{chinese ? "完整产品说明" : "Full product specification"}</span><strong>{productSpec?.path ?? "docs/product-spec.md"}</strong></div>
          <button type="button" onClick={onOpenDocument} disabled={!productSpec}><FileText size={16} />{chinese ? "查看完整产品说明" : "Open full specification"}</button>
        </div>
      </div>
    </div>
    <div className="approval-bar"><div><strong>{chinese ? "确认当前产品方案？" : "Approve this product plan?"}</strong><span>{chinese ? "确认对象是产品说明及其中记录的能力边界，不是视觉稿。" : "You are approving the product specification and its capability boundary, not a visual mockup."}</span></div><button onClick={approve} disabled={approving || !productSpec || summaryDirty || Boolean(updating)}>{approving ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} {chinese ? "确认并构建" : "Confirm and build"}</button></div>
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
  const draftReady = revised.trim().length >= 4;
  const submit = async () => {
    if (!draftReady || submitting) return;
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
        <h1>{ui(language, "Confirm the requirement draft")}</h1>
        <p>{ui(language, "Product Manager expanded the original goal into a buildable Web requirement.")}</p>
        {blueprint?.capability_policy_version !== "catalog-v1" && <p>{reason}</p>}
        <small><CircleAlert size={14} /> {ui(language, "Review the behavior, interactions, states, and visual direction before building.")}</small>
      </div>
    </div>
    <div className="scope-revise">
      <label>{ui(language, "Requirement draft")}
        <textarea value={revised} onChange={(event) => setRevised(event.target.value)} placeholder={rewrite || ui(language, "Describe the product behavior, interactions, states, and visual direction…")} maxLength={4000} rows={4} autoFocus />
      </label>
      <p className="scope-hint"><Sparkles size={13} /> {ui(language, "Confirmation skips Product Manager and continues directly to architecture.")}</p>
      <div className="scope-actions">
        <button className="secondary-action" disabled={!revised.trim() || regenerating || submitting} onClick={regenerate}>{regenerating ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />} {ui(language, "Regenerate requirement draft")}</button>
        <button className="primary-action" disabled={!draftReady || submitting || regenerating} onClick={submit}>{submitting ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />} {ui(language, "Confirm requirement & build")}</button>
      </div>
      <small className="scope-regenerate-note">{ui(language, "Product Manager will reinterpret the text and return a new requirement draft without starting a build.")}</small>
    </div>
  </div>;
}

function ClarificationState({ run, language }: { run: RunView; language: Language }) {
  const task = run.pending_human_task;
  return <div className="center-state scope-stop clarification-state">
    <div className="pm-feedback-card">
      <RoleAvatar role="product" size="large" />
      <div>
        <span>{ui(language, "Product Manager feedback")}</span>
        <h1>{language === "zh" ? "产品经理需要你补充一项信息" : "Product Manager needs one clarification"}</h1>
        <p>{task?.prompt}</p>
        <small><CircleAlert size={14} /> {language === "zh" ? "回复后会恢复当前任务，不会重新创建 Project。" : "Your reply resumes this Run instead of creating another Project."}</small>
      </div>
    </div>
  </div>;
}

function StaleClarificationState({ language }: { language: Language }) {
  return <div className="center-state scope-stop clarification-state">
    <div className="pm-feedback-card">
      <RoleAvatar role="product" size="large" />
      <div>
        <span>{ui(language, "Product Manager feedback")}</span>
        <h1>{language === "zh" ? "这次澄清已失效" : "This clarification has expired"}</h1>
        <p>{ui(language, "This clarification expired because the Project changed. Send the change again from the current version.")}</p>
      </div>
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
      const routed = await api.sendProjectMessage(run.project_id, run.prompt, run.model);
      if (!routed.proposal_id) throw new Error(ui(language, "The retry request did not produce a code change proposal."));
      const created = await api.approveProjectChange(run.project_id, routed.proposal_id);
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

function BuildingState({ run, events, language }: { run: RunView; events: RunEvent[]; language: Language }) {
  const roles: Record<string, RoleKey> = {
    team_leader: "leader",
    product_manager: "product",
    build_queue: "validator",
    architect: "architect",
    engineer: "engineer",
    data: "data",
    build: "validator",
    reviewer: "reviewer",
    complete: "reviewer",
  };
  const role = roles[run.current_stage] ?? "leader";
  const title = BUILDING_STAGE_TITLES[language][run.current_stage] ?? `${stageLabel(language, run.current_stage)} ${ui(language, "is working")}`;
  const latest = [...events].reverse().find((event) => {
    const stage = event.payload.stage;
    return stage === run.current_stage || (run.current_stage === "engineer" && stage === "engineer_repair");
  });
  const [now, setNow] = useState(Date.now());
  const waitingForModel = latest?.type === "agent.attempt.started";
  useEffect(() => {
    if (!waitingForModel) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [latest?.event_id, waitingForModel]);
  const modelRequestStartedAt = latest && waitingForModel ? eventTimestampMs(latest.timestamp) : null;
  const elapsed = modelRequestStartedAt === null ? 0 : Math.max(0, Math.floor((now - modelRequestStartedAt) / 1000));
  return <div className="center-state building-cartoon">
    <div className="working-avatar"><RoleAvatar role={role} size="hero" /></div>
    <div className="working-stage"><LoaderCircle className="spin" size={15} /><span>{stageLabel(language, run.current_stage)}</span></div>
    <h1>{title}</h1>
    <p>{latest ? eventMessage(language, latest) : ui(language, "The current stage is persisted. Refreshing this page will not lose the run.")}</p>
    {waitingForModel && <small>{language === "zh" ? `已等待 ${elapsed} 秒；模型返回后将继续解析、校验并保存本阶段结果。` : `Waiting for ${elapsed}s; the stage result will then be parsed, validated, and saved.`}</small>}
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
    <ProjectChatPanel run={run} refreshShell={refreshShell} refreshRun={refreshRun} setError={setError} language={language} />
    {deploymentUrl && <div className="published-banner"><Check size={16} /><span>{ui(language, "Published successfully")}</span><a href={deploymentUrl} target="_blank" rel="noreferrer">{ui(language, "Open public app")} <ExternalLink size={14} /></a></div>}
    {tab === "preview" && current && <div className="preview-stage"><div className={device === "mobile" ? "preview-frame mobile" : "preview-frame"}><iframe key={`${current.id}-${previewKey}`} src={`/preview/${current.id}`} title={ui(language, "Generated application preview")} /></div></div>}
    {tab === "edit" && <div className="edit-panel"><div className="content-heading"><div><span>{ui(language, "Structured edit")}</span><h1>{ui(language, "Refine the current version")}</h1><p>{ui(language, "Saving creates a new ProjectVersion and keeps the original.")}</p></div></div><label>{ui(language, "Hero title")}<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>{ui(language, "Hero body")}<textarea value={body} onChange={(e) => setBody(e.target.value)} /></label><label>{ui(language, "Primary color")}<div className="color-input"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /><input value={color} onChange={(e) => setColor(e.target.value)} /></div></label><button className="primary-action" onClick={save}><Check size={16} /> {ui(language, "Save as new version")}</button></div>}
    {tab === "versions" && <div className="versions-panel"><div className="content-heading"><div><span>{ui(language, "Project history")}</span><h1>{ui(language, "Versions")}</h1><p>{ui(language, "Restore always creates a new version; history is never overwritten.")}</p></div></div>{versions.map((version) => <div className="version-row" key={version.id}><span className="version-number">v{version.number}</span><div><strong>{version.summary}</strong><small>{new Date(version.created_at).toLocaleString()}</small></div>{version.id === run.version_id ? <b>{ui(language, "Current")}</b> : <button onClick={async () => { const restored = await api.restore(run.project_id, version.id); setVersions([restored, ...versions]); await refreshRun(run.run_id); }}>{ui(language, "Restore")}</button>}</div>)}</div>}
  </div>;
}

function ProjectChatPanel({ run, refreshShell, refreshRun, setError, language }: { run: RunView; refreshShell: () => Promise<void>; refreshRun: (id: string) => Promise<RunView>; setError: (value: string) => void; language: Language }) {
  const [changeMessage, setChangeMessage] = useState("");
  const [changeSubmitting, setChangeSubmitting] = useState(false);
  const [projectMessages, setProjectMessages] = useState<ProjectMessageView[]>([]);
  const [messagesError, setMessagesError] = useState("");
  const [approvingProposalId, setApprovingProposalId] = useState("");
  useEffect(() => {
    let active = true;
    api.projectMessages(run.project_id)
      .then((messages) => { if (active) { setProjectMessages(messages); setMessagesError(""); } })
      .catch((reason) => { if (active) setMessagesError(reason instanceof Error ? reason.message : ui(language, "Could not load Project messages")); });
    return () => { active = false; };
  }, [language, run.project_id, run.run_id]);
  const submitChange = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!changeMessage.trim() || changeSubmitting) return;
    setChangeSubmitting(true);
    setError("");
    try {
      if (run.pending_human_task?.kind === "input_request") {
        const created = await api.respondHumanTask(run.pending_human_task.id, changeMessage.trim());
        setChangeMessage("");
        await refreshRun(created.run_id);
        await refreshShell();
        return;
      }
      const result: ProjectMessageResult = await api.sendProjectMessage(run.project_id, changeMessage.trim(), run.model);
      setChangeMessage("");
      setProjectMessages((current) => [...current, result.user_message, result.lead_message]);
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "BASE_VERSION_CHANGED") {
        await refreshRun(run.run_id);
        await refreshShell();
        setError(ui(language, "This clarification expired because the Project changed. Send the change again from the current version."));
      } else {
        setError(reason instanceof Error ? reason.message : ui(language, "Could not start Project change"));
      }
    } finally {
      setChangeSubmitting(false);
    }
  };
  const approveProposal = async (proposal: ProjectMessageView) => {
    if (approvingProposalId) return;
    setApprovingProposalId(proposal.id);
    setError("");
    try {
      const created = await api.approveProjectChange(run.project_id, proposal.id);
      setProjectMessages((current) => current.map((message) => message.id === proposal.id ? { ...message, payload: { ...message.payload, status: "approved", run_id: created.run_id } } : message));
      await refreshRun(created.run_id);
      await refreshShell();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "BASE_VERSION_CHANGED") {
        setProjectMessages((current) => current.map((message) => message.id === proposal.id ? { ...message, payload: { ...message.payload, status: "stale" } } : message));
        await refreshShell();
      }
      setError(reason instanceof Error ? reason.message : ui(language, "Could not start Project change"));
    } finally {
      setApprovingProposalId("");
    }
  };
  return <section className="project-chat-panel">
    <div className="project-chat-heading"><MessageCircle size={17} /><div><strong>{ui(language, "Project conversation")}</strong><small>{ui(language, "Ask about the Project or describe what you want to change.")}</small></div></div>
    {messagesError && <div className="inline-error"><CircleAlert size={15} /> {messagesError}</div>}
    {projectMessages.length > 0 && <div className="project-chat-history">{projectMessages.slice(-20).map((message) => <div className={`project-chat-message ${message.role}${message.message_type === "change_proposal" ? " proposal" : ""}`} key={message.id}><b>{message.role === "user" ? (language === "zh" ? "你" : "You") : message.role === "lead" ? roleLabel(language, "leader") : (language === "zh" ? "系统" : "System")}</b><span>{message.content}</span>{message.message_type === "change_proposal" && <div className="project-change-proposal"><strong>{String(message.payload.change_summary ?? (language === "zh" ? "修改当前项目" : "Modify the current Project"))}</strong><small>{language === "zh" ? "确认后才会创建修改 Run 并写入代码。" : "A change Run and code write start only after confirmation."}</small><button type="button" onClick={() => void approveProposal(message)} disabled={message.payload.status !== "pending" || Boolean(approvingProposalId)}>{approvingProposalId === message.id ? <LoaderCircle className="spin" size={14} /> : <Code2 size={14} />}{message.payload.status === "approved" ? (language === "zh" ? "已开始修改" : "Change started") : message.payload.status === "stale" ? (language === "zh" ? "已失效" : "Expired") : (language === "zh" ? "修改代码" : "Modify code")}</button></div>}</div>)}</div>}
    <form onSubmit={submitChange}><textarea value={changeMessage} onChange={(event) => setChangeMessage(event.target.value)} maxLength={4000} rows={2} placeholder={run.pending_human_task?.kind === "input_request" ? run.pending_human_task.prompt : (language === "zh" ? "询问当前项目，或描述你希望修改的内容。" : "Ask about the current Project or describe a change.")} /><button className="primary-action" type="submit" disabled={!changeMessage.trim() || changeSubmitting}>{changeSubmitting ? <LoaderCircle className="spin" size={16} /> : <ArrowUp size={16} />} {run.pending_human_task?.kind === "input_request" ? (language === "zh" ? "提交补充" : "Send clarification") : (language === "zh" ? "发送" : "Send")}</button></form>
  </section>;
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
