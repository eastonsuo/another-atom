import {
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Download,
  FolderKanban,
  LoaderCircle,
  LogOut,
  RefreshCw,
  Search,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AtomLogo } from "./components/BrandAssets";
import { api } from "./lib/api";
import type {
  AdminProjectDetail,
  AdminProjectList,
  AdminProjectSummary,
  AdminUserList,
  AdminUserSummary,
  AdminUserView,
} from "./types";

const STAGES: Record<string, string> = {
  product_manager: "产品经理整理需求",
  blueprint_approval: "等待用户确认方案",
  scope_review: "等待用户补充需求",
  build_queue: "构建队列",
  architect: "架构师设计",
  engineer: "工程师生成代码",
  data: "数据分析",
  build: "构建与校验",
  reviewer: "独立审查",
  complete: "预览就绪",
};

const RUN_STATUS: Record<string, string> = {
  product_running: "进行中",
  awaiting_approval: "等待确认",
  needs_input: "等待补充",
  build_queued: "已排队",
  architect_running: "进行中",
  engineer_running: "进行中",
  building: "进行中",
  data_running: "进行中",
  review_running: "进行中",
  completed: "已完成",
  completed_degraded: "已完成，有警告",
  failed: "失败",
  cancelled: "已取消",
};

const PROJECT_STATUS: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  ready: "已就绪",
  live: "已发布",
  paused: "已暂停",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function runStage(project: AdminProjectSummary): string {
  const run = project.latest_run;
  if (!run) return "未开始";
  const stage = STAGES[run.current_stage] ?? `未识别阶段：${run.current_stage}`;
  if (run.status === "failed") return run.current_stage === "complete" ? "任务失败" : `${stage}阶段失败`;
  if (run.status === "cancelled") return run.current_stage === "complete" ? "任务已取消" : `${stage}阶段已取消`;
  return stage;
}

export function AdminApp() {
  const [admin, setAdmin] = useState<AdminUserView | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    api.adminMe()
      .then(setAdmin)
      .catch(() => setAdmin(null))
      .finally(() => setChecked(true));
  }, []);

  if (!checked) return <div className="admin-loading"><LoaderCircle className="spin" /></div>;
  if (!admin) return <AdminLogin onAuthenticated={setAdmin} />;
  return <AdminDashboard admin={admin} />;
}

function AdminLogin({ onAuthenticated }: { onAuthenticated: (user: AdminUserView) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!/^[a-zA-Z0-9_-]{3,80}$/.test(username)) {
      setError("请输入有效的管理员用户名。");
      return;
    }
    if (password.length < 10) {
      setError("密码至少需要 10 个字符。");
      return;
    }
    setSubmitting(true);
    try {
      const user = await api.adminLogin(username, password);
      window.history.replaceState({}, "", "/admin");
      onAuthenticated(user);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "管理员登录失败";
      setError(message === "Administrator access is required" ? "该账户没有管理员权限。" : message === "Username or password is incorrect" ? "用户名或密码不正确。" : message === "Too many failed sign-in attempts; try again later" ? "失败次数过多，请稍后再试。" : message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="admin-auth">
      <form className="admin-auth-card" onSubmit={submit}>
        <div className="admin-brand"><AtomLogo /><strong>Another Atom</strong></div>
        <span><ShieldCheck size={15} /> 管理后台</span>
        <h1>管理员登录</h1>
        <p>查看注册用户、Project 和最新执行状态。</p>
        <label>用户名<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label>密码<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error && <div className="admin-error" role="alert"><CircleAlert size={16} />{error}</div>}
        <button className="admin-primary" disabled={submitting} type="submit">
          {submitting ? <LoaderCircle className="spin" size={16} /> : <ShieldCheck size={16} />}
          登录管理后台
        </button>
        {import.meta.env.DEV && <small>默认开发账号：admin / admin12345</small>}
      </form>
    </main>
  );
}

function AdminDashboard({ admin }: { admin: AdminUserView }) {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [users, setUsers] = useState<AdminUserList | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [projects, setProjects] = useState<Record<string, AdminProjectList>>({});
  const [loadingProjects, setLoadingProjects] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdminProjectDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [promotingUserId, setPromotingUserId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUsers(await api.adminUsers(query, page));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "用户列表加载失败");
    } finally {
      setLoading(false);
    }
  }, [page, query]);

  useEffect(() => {
    let active = true;
    api.adminUsers(query, page)
      .then((result) => { if (active) setUsers(result); })
      .catch((reason: Error) => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [page, query]);

  const loadProjects = async (userId: string, projectPage: number) => {
    setLoadingProjects(userId);
    setError("");
    try {
      const next = await api.adminUserProjects(userId, projectPage);
      setProjects((current) => ({ ...current, [userId]: next }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project 加载失败");
    } finally {
      setLoadingProjects(null);
    }
  };

  const toggleUser = async (user: AdminUserSummary) => {
    if (expanded === user.id) {
      setExpanded(null);
      return;
    }
    setExpanded(user.id);
    if (projects[user.id]) return;
    await loadProjects(user.id, 1);
  };

  const openDetail = async (projectId: string) => {
    setError("");
    try {
      setDetail(await api.adminProject(projectId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Project 详情加载失败");
    }
  };

  const promoteUser = async (user: AdminUserSummary) => {
    if (promotingUserId) return;
    const confirmed = window.confirm(`确认将 ${user.display_name}（@${user.username}）设为管理员？该账户将可以查看所有用户与 Project，并继续配置其他管理员。`);
    if (!confirmed) return;
    setPromotingUserId(user.id);
    setError("");
    setNotice("");
    try {
      await api.adminPromoteUser(user.id);
      setUsers((current) => current ? {
        ...current,
        items: current.items.filter((item) => item.id !== user.id),
        total: Math.max(0, current.total - 1),
      } : current);
      setExpanded((current) => current === user.id ? null : current);
      setNotice(`${user.display_name} 已设为管理员。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "管理员权限配置失败");
    } finally {
      setPromotingUserId(null);
    }
  };

  const lastPage = Math.max(1, Math.ceil((users?.total ?? 0) / (users?.page_size ?? 20)));
  return (
    <div className="admin-shell">
      <header className="admin-header">
        <div className="admin-brand"><AtomLogo /><div><span>运营与权限后台</span><strong>Another Atom Admin</strong></div></div>
        <div><span className="admin-account"><ShieldCheck size={14} />{admin.display_name}</span><button onClick={async () => { await api.logout(); window.location.assign("/admin/login"); }}><LogOut size={15} />退出</button></div>
      </header>
      <main className="admin-main">
        <section className="admin-title">
          <div><span>V1 SYSTEM OVERVIEW</span><h1>用户与项目</h1><p>查看注册用户和 Project 状态，并配置管理员权限。</p></div>
          <button className="admin-refresh" onClick={() => void loadUsers()}><RefreshCw size={16} />刷新</button>
        </section>
        <form className="admin-search" onSubmit={(event) => { event.preventDefault(); setPage(1); setQuery(queryInput.trim()); }}>
          <Search size={17} /><input placeholder="搜索显示名称或用户名" value={queryInput} onChange={(event) => setQueryInput(event.target.value)} /><button type="submit">搜索</button>
        </form>
        {error && <div className="admin-error" role="alert"><CircleAlert size={16} />{error}<button onClick={() => setError("")}><X size={14} /></button></div>}
        {notice && <div className="admin-notice" role="status"><ShieldCheck size={16} />{notice}<button onClick={() => setNotice("")}><X size={14} /></button></div>}
        <section className="admin-users-card">
          <div className="admin-list-head"><span><Users size={16} />注册用户</span><b>{users?.total ?? 0}</b></div>
          {loading ? <div className="admin-empty"><LoaderCircle className="spin" />正在加载用户……</div> : users?.items.length ? users.items.map((user) => (
            <div className="admin-user-block" key={user.id}>
              <button className="admin-user-row" onClick={() => void toggleUser(user)}>
                {expanded === user.id ? <ChevronDown size={17} /> : <ChevronRight size={17} />}
                <span><strong>{user.display_name}</strong><small>@{user.username} · 注册于 {formatDate(user.created_at)}</small></span>
                <span><b>{user.project_count}</b><small>Project</small></span>
                <span><b>{user.quota_used}</b><small>已使用配额</small></span>
                <em>{user.plan}</em>
              </button>
              {expanded === user.id && <div className="admin-projects">
                <div className="admin-user-actions"><div><ShieldCheck size={16} /><span><strong>管理员权限</strong><small>管理员可查看所有用户、Project 和 Run 日志，并配置其他管理员。</small></span></div><button disabled={Boolean(promotingUserId)} onClick={() => void promoteUser(user)}>{promotingUserId === user.id ? <LoaderCircle className="spin" size={14} /> : <ShieldCheck size={14} />}设为管理员</button></div>
                {loadingProjects === user.id ? <div className="admin-empty"><LoaderCircle className="spin" />正在加载 Project……</div> : projects[user.id]?.items.length ? <>{projects[user.id].items.map((project) => <ProjectRow project={project} onOpen={openDetail} key={project.id} />)}<ProjectPagination projects={projects[user.id]} onPage={(nextPage) => void loadProjects(user.id, nextPage)} /></> : <div className="admin-empty">该用户还没有 Project。</div>}
              </div>}
            </div>
          )) : <div className="admin-empty">没有匹配的注册用户。</div>}
          <div className="admin-pagination"><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>上一页</button><span>第 {page} / {lastPage} 页</span><button disabled={page >= lastPage} onClick={() => setPage((value) => value + 1)}>下一页</button></div>
        </section>
      </main>
      {detail && <ProjectDrawer detail={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function ProjectPagination({ projects, onPage }: { projects: AdminProjectList; onPage: (page: number) => void }) {
  const lastPage = Math.max(1, Math.ceil(projects.total / projects.page_size));
  if (lastPage <= 1) return null;
  return <div className="admin-project-pagination"><button disabled={projects.page <= 1} onClick={() => onPage(projects.page - 1)}>上一页</button><span>Project 第 {projects.page} / {lastPage} 页</span><button disabled={projects.page >= lastPage} onClick={() => onPage(projects.page + 1)}>下一页</button></div>;
}

function ProjectRow({ project, onOpen }: { project: AdminProjectSummary; onOpen: (id: string) => void }) {
  const run = project.latest_run;
  return <button className="admin-project-row" onClick={() => onOpen(project.id)}>
    <FolderKanban size={18} />
    <span><strong>{project.name}</strong><small>{project.summary}</small></span>
    <span><b>{PROJECT_STATUS[project.status] ?? project.status}</b><small>Project 状态</small></span>
    <span><b>{runStage(project)}</b><small>{run ? RUN_STATUS[run.status] ?? run.status : "无 Run"}</small></span>
    <span><b>{formatDate(project.updated_at)}</b><small>最近更新</small></span>
    <ChevronRight size={17} />
  </button>;
}

function ProjectDrawer({ detail, onClose }: { detail: AdminProjectDetail; onClose: () => void }) {
  const { project } = detail;
  const run = project.latest_run;
  return <div className="admin-drawer-backdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
    <aside className="admin-drawer">
      <header><div><span>PROJECT DETAIL</span><h2>{project.name}</h2></div><button onClick={onClose}><X size={18} /></button></header>
      <section><h3>项目简介</h3><p>{project.summary}</p><dl><div><dt>Project ID</dt><dd>{project.id}</dd></div><div><dt>状态</dt><dd>{PROJECT_STATUS[project.status] ?? project.status}</dd></div><div><dt>原始需求</dt><dd>{detail.prompt_summary || "暂无"}</dd></div><div><dt>支持等级</dt><dd>{project.support_level ?? "尚未生成 Blueprint"}</dd></div></dl></section>
      <section><h3>最新执行</h3>{run ? <><dl><div><dt>Run ID</dt><dd>{run.id}</dd></div><div><dt>阶段</dt><dd>{runStage(project)}</dd></div><div><dt>结果</dt><dd>{RUN_STATUS[run.status] ?? run.status}</dd></div><div><dt>模型</dt><dd>{run.model}</dd></div><div><dt>用量</dt><dd>{run.quota_spent}</dd></div></dl>{run.error_code && <div className="admin-run-error"><b>{run.error_code}</b><p>{run.error_summary}</p></div>}<a className="admin-download" href={api.adminRunLog(run.id)} download><Download size={15} />下载完整 Run 日志</a></> : <p>该 Project 还没有 Run。</p>}</section>
      <section><h3>最近事件</h3><div className="admin-events">{detail.events.length ? [...detail.events].reverse().slice(0, 20).map((event) => <div key={event.event_id}><time>{formatDate(event.timestamp)}</time><b>{event.type}</b><p>{String(event.payload.message ?? event.type)}</p></div>) : <p>暂无持久化事件。</p>}</div></section>
    </aside>
  </div>;
}
