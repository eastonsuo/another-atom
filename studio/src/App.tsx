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
import { AtomLogo, ROLE_META, RoleAvatar, type RoleKey } from "./components/BrandAssets";
import { api } from "./lib/api";
import type {
  AttachmentMeta,
  Blueprint,
  Mode,
  ProjectView,
  QuotaView,
  RunEvent,
  RunView,
  VersionView,
} from "./types";

const EXAMPLE_PROMPTS = [
  "Build a restrained product catalog called Mono Market for useful home objects. Use editorial photography and warm neutral colors.",
  "Create a modern lighting collection with Home, Catalog, and Product pages. Make the typography crisp and the accent color coral.",
];

const TERMINAL = new Set(["completed", "completed_degraded", "failed", "cancelled", "needs_input"]);

export function App() {
  const previewMatch = window.location.pathname.match(/^\/preview\/([^/]+)/);
  const publicMatch = window.location.pathname.match(/^\/apps\/([^/]+)/);
  if (previewMatch) return <PreviewLoader kind="preview" id={previewMatch[1]} />;
  if (publicMatch) return <PreviewLoader kind="public" id={publicMatch[1]} />;
  return <Studio />;
}

function Studio() {
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<Mode>("team");
  const [attachments, setAttachments] = useState<AttachmentMeta[]>([]);
  const [run, setRun] = useState<RunView | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [projects, setProjects] = useState<ProjectView[]>([]);
  const [versions, setVersions] = useState<VersionView[]>([]);
  const [quota, setQuota] = useState<QuotaView | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [tab, setTab] = useState<"preview" | "edit" | "versions">("preview");

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

  useEffect(() => { refreshShell().catch(() => undefined); }, [refreshShell]);
  useEffect(() => {
    if (!run) return;
    const source = new EventSource(`/api/runs/${run.run_id}/events`);
    const eventTypes = [
      "stage.started",
      "stage.completed",
      "artifact.created",
      "agent.retry",
      "approval.required",
      "approval.confirmed",
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
  }, [run?.run_id]);
  useEffect(() => {
    if (!run || TERMINAL.has(run.status) || run.status === "awaiting_approval") return;
    const timer = window.setInterval(() => {
      refreshRun(run.run_id).then((next) => {
        if (TERMINAL.has(next.status)) refreshShell().catch(() => undefined);
      }).catch((reason: Error) => setError(reason.message));
    }, 700);
    return () => window.clearInterval(timer);
  }, [refreshRun, refreshShell, run]);

  const createRun = async () => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const created = await api.createRun(prompt, mode, attachments);
      setRun(created);
      setEvents(await api.events(created.run_id));
      setVersions([]);
      await refreshShell();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the run");
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
      setError(reason instanceof Error ? reason.message : "Could not open the project");
    }
  };

  const resetComposer = () => {
    setRun(null);
    setEvents([]);
    setVersions([]);
    setPrompt("");
    setAttachments([]);
    setError("");
  };

  return (
    <div className="studio-shell">
      <Sidebar
        projects={projects}
        quota={quota}
        activeProjectId={run?.project_id}
        onNew={resetComposer}
        onOpen={openProject}
      />
      <main className={run ? "studio-main active" : "studio-main"}>
        <header className="studio-topbar">
          <div>
            <span className="topbar-context">{run ? "Project workspace" : "Application studio"}</span>
            <strong>{run?.blueprint?.project_name ?? "Another Atom"}</strong>
          </div>
          {run && <StatusPill status={run.status} />}
        </header>
        {!run ? (
          <Composer
            prompt={prompt}
            setPrompt={setPrompt}
            mode={mode}
            setMode={setMode}
            attachments={attachments}
            setAttachments={setAttachments}
            submitting={submitting}
            error={error}
            createRun={createRun}
          />
        ) : (
          <Workspace
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
  onNew,
  onOpen,
}: {
  projects: ProjectView[];
  quota: QuotaView | null;
  activeProjectId?: string;
  onNew: () => void;
  onOpen: (project: ProjectView) => void;
}) {
  return (
    <aside className="studio-sidebar">
      <div className="brand"><AtomLogo /><strong>Another Atom</strong></div>
      <button className="new-project" onClick={onNew}><Plus size={17} /> New project</button>
      <div className="sidebar-section">
        <span className="sidebar-label">Projects</span>
        <div className="project-list">
          {projects.length === 0 && <p className="sidebar-empty">Your generated projects will appear here.</p>}
          {projects.map((project) => (
            <button
              key={project.id}
              className={project.id === activeProjectId ? "project-link active" : "project-link"}
              onClick={() => onOpen(project)}
            >
              <span className="project-icon"><Layers3 size={15} /></span>
              <span><strong>{project.name}</strong><small>{project.status}</small></span>
              <ChevronRight size={15} />
            </button>
          ))}
        </div>
      </div>
      <div className="quota-panel">
        <div><span>Demo usage</span><strong>{quota?.remaining ?? "–"} left</strong></div>
        <div className="quota-track"><span style={{ width: `${quota ? (quota.used / quota.limit) * 100 : 0}%` }} /></div>
        <small>Mock LLM units are shared across sessions.</small>
      </div>
    </aside>
  );
}

function Composer({
  prompt,
  setPrompt,
  mode,
  setMode,
  attachments,
  setAttachments,
  submitting,
  error,
  createRun,
}: {
  prompt: string;
  setPrompt: (value: string) => void;
  mode: Mode;
  setMode: (mode: Mode) => void;
  attachments: AttachmentMeta[];
  setAttachments: (items: AttachmentMeta[]) => void;
  submitting: boolean;
  error: string;
  createRun: () => void;
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
        <span className="notice"><Sparkles size={14} /> Mock LLM is active</span>
        <div className="crew-stage" aria-label="Your build team">
          <span className="crew-spark spark-one" />
          <span className="crew-spark spark-two" />
          {(["product", "designer", "engineer", "qa"] as RoleKey[]).map((role) => (
            <div className="crew-member" key={role}>
              <RoleAvatar role={role} size="large" />
              <span>{ROLE_META[role].label}</span>
            </div>
          ))}
        </div>
        <h1>What should the team build?</h1>
        <p>Describe a product showcase or catalog. You will review the plan before any build starts.</p>
      </div>
      <div className="composer-box">
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="A product catalog called Mono Market for carefully selected home objects…"
          maxLength={4000}
          autoFocus
        />
        {attachments.length > 0 && (
          <div className="attachment-row">
            {attachments.map((attachment) => (
              <span key={attachment.name}><Paperclip size={13} /> {attachment.name}<button aria-label={`Remove ${attachment.name}`} title="Remove attachment" onClick={() => setAttachments(attachments.filter((item) => item !== attachment))}><X size={13} /></button></span>
            ))}
          </div>
        )}
        <div className="composer-actions">
          <label className="attach-button" title="Add reference attachments"><Paperclip size={17} /><input type="file" multiple onChange={addFiles} /></label>
          <div className="mode-switch" aria-label="Build mode">
            <button className={mode === "engineer" ? "active" : ""} onClick={() => setMode("engineer")} title="Fast, narrow build"><Code2 size={15} /> Engineer</button>
            <button className={mode === "team" ? "active" : ""} onClick={() => setMode("team")} title="Inspectable staged pipeline"><Users size={15} /> Team</button>
          </div>
          <button className="submit-prompt" disabled={!prompt.trim() || submitting} onClick={createRun} aria-label="Build application" title="Build application">
            {submitting ? <LoaderCircle className="spin" size={19} /> : <ArrowUp size={19} />}
          </button>
        </div>
      </div>
      {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
      <div className="example-prompts">
        <span>Start with an example</span>
        {EXAMPLE_PROMPTS.map((example, index) => <button key={example} onClick={() => setPrompt(example)}><span>0{index + 1}</span>{example}</button>)}
      </div>
    </section>
  );
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
}: {
  run: RunView;
  setRun: (run: RunView) => void;
  events: RunEvent[];
  versions: VersionView[];
  setVersions: (versions: VersionView[]) => void;
  device: "desktop" | "mobile";
  setDevice: (device: "desktop" | "mobile") => void;
  tab: "preview" | "edit" | "versions";
  setTab: (tab: "preview" | "edit" | "versions") => void;
  refreshShell: () => Promise<void>;
  refreshRun: (runId: string) => Promise<RunView>;
  error: string;
  setError: (error: string) => void;
}) {
  const [approving, setApproving] = useState(false);
  const [blueprint, setBlueprint] = useState<Blueprint | null>(run.blueprint);
  const ready = run.status === "completed" || run.status === "completed_degraded";
  useEffect(() => setBlueprint(run.blueprint), [run.blueprint]);

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
        <div className="panel-heading"><div><span>Staged pipeline</span><h2>Build activity</h2></div><ModeBadge mode={run.mode} /></div>
        <Timeline run={run} events={events} />
        {error && <div className="inline-error"><CircleAlert size={16} /> {error}</div>}
      </section>
      <section className="workspace-content">
        {run.status === "awaiting_approval" && blueprint ? (
          <BlueprintEditor blueprint={blueprint} setBlueprint={setBlueprint} approve={approve} approving={approving} />
        ) : run.status === "needs_input" && blueprint ? (
          <ScopeStop blueprint={blueprint} />
        ) : run.status === "failed" ? (
          <FailedState run={run} />
        ) : ready && run.version_id ? (
          <ResultWorkspace
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
          />
        ) : (
          <BuildingState run={run} />
        )}
      </section>
    </div>
  );
}

function Timeline({ run, events }: { run: RunView; events: RunEvent[] }) {
  const stages = run.mode === "team"
    ? ["product_manager", "blueprint_approval", "designer", "engineer", "build", "qa", "complete"]
    : ["product_manager", "blueprint_approval", "engineer", "build", "complete"];
  const labels: Record<string, string> = { product_manager: "Product Manager", blueprint_approval: "Your approval", designer: "Designer", engineer: "Engineer", build: "Renderer", qa: "QA", complete: "Preview ready", build_queue: "Build queue", scope_review: "Scope review" };
  const roles: Record<string, RoleKey> = { product_manager: "product", blueprint_approval: "user", designer: "designer", engineer: "engineer", build: "renderer", qa: "qa", complete: "qa" };
  const currentIndex = stages.indexOf(run.current_stage);
  return <div className="timeline">
    {stages.map((stage, index) => {
      const completed = currentIndex > index || TERMINAL.has(run.status) && run.status.startsWith("completed");
      const active = run.current_stage === stage || (run.current_stage === "build_queue" && stage === "engineer");
      return <div className={active ? "timeline-item active" : completed ? "timeline-item complete" : "timeline-item"} key={stage}>
        <div className="timeline-avatar"><RoleAvatar role={roles[stage]} size="small" /><span className="timeline-state">{completed ? <Check size={10} /> : active ? <LoaderCircle className="spin" size={10} /> : index + 1}</span></div>
        <div><strong>{labels[stage]}</strong><small>{active ? "In progress" : completed ? "Complete" : "Waiting"}</small></div>
      </div>;
    })}
    <div className="event-log">
      <span>Recent events</span>
      {events.slice(-5).reverse().map((event) => <div key={event.event_id}><i /> <p>{event.payload.message}</p></div>)}
    </div>
  </div>;
}

function BlueprintEditor({ blueprint, setBlueprint, approve, approving }: { blueprint: Blueprint; setBlueprint: (value: Blueprint) => void; approve: () => void; approving: boolean }) {
  return <div className="blueprint-view">
    <div className="content-heading blueprint-heading"><RoleAvatar role="product" size="large" /><div><span>Product Manager · Approval gate</span><h1>Confirm what we will build</h1><p>The build cannot start until this structured Blueprint is approved.</p></div><SupportBadge level={blueprint.support_level} /></div>
    {blueprint.support_level === "adapted" && <div className="scope-note"><CircleAlert size={17} /><div><strong>Some requirements were adapted</strong><p>{blueprint.omitted_requirements.join(" ")}</p></div></div>}
    <div className="blueprint-form">
      <label>Project name<input value={blueprint.project_name} onChange={(e) => setBlueprint({ ...blueprint, project_name: e.target.value })} /></label>
      <label>Visual direction<textarea value={blueprint.visual_direction} onChange={(e) => setBlueprint({ ...blueprint, visual_direction: e.target.value })} /></label>
      <div className="blueprint-group"><span>Pages</span><div className="token-row">{blueprint.pages.map((page) => <b key={page}>{page}</b>)}</div></div>
      <div className="blueprint-group"><span>Modules</span><div className="token-row">{blueprint.modules.map((module) => <b key={module}>{module}</b>)}</div></div>
      <div className="blueprint-group"><span>Mapped requirements</span><ul>{blueprint.mapped_requirements.map((item) => <li key={item}><Check size={15} /> {item}</li>)}</ul></div>
    </div>
    <div className="approval-bar"><div><strong>Ready to continue?</strong><span>This records an explicit approval.</span></div><button onClick={approve} disabled={approving || !blueprint.project_name.trim()}>{approving ? <LoaderCircle className="spin" size={17} /> : <Check size={17} />} Approve & build</button></div>
  </div>;
}

function ScopeStop({ blueprint }: { blueprint: Blueprint }) {
  return <div className="center-state"><span className="state-icon warning"><CircleAlert /></span><h1>Request needs to be narrowed</h1><p>{blueprint.support_reasons[0]}</p><div className="rewrite-box"><span>Suggested rewrite</span><p>{blueprint.rewrite_suggestion}</p></div></div>;
}

function FailedState({ run }: { run: RunView }) {
  return <div className="center-state"><span className="state-icon error"><X /></span><h1>Run stopped</h1><p>{run.error_message}</p><code>{run.error_code}</code><span>Your project and original request are still saved.</span></div>;
}

function BuildingState({ run }: { run: RunView }) {
  const role: RoleKey = run.current_stage === "designer" ? "designer" : run.current_stage === "qa" ? "qa" : run.current_stage === "build" ? "renderer" : "engineer";
  return <div className="center-state building-cartoon"><div className="working-avatar"><RoleAvatar role={role} size="hero" /><span><LoaderCircle className="spin" /></span></div><h1>{run.current_stage === "build_queue" ? "Build queued" : `${ROLE_META[role].label} is working`}</h1><p>The current stage is persisted. Refreshing this page will not lose the run.</p><div className="build-meter"><span /></div></div>;
}

function ResultWorkspace({ run, versions, setVersions, device, setDevice, tab, setTab, refreshShell, refreshRun, setError }: { run: RunView; versions: VersionView[]; setVersions: (v: VersionView[]) => void; device: "desktop" | "mobile"; setDevice: (v: "desktop" | "mobile") => void; tab: "preview" | "edit" | "versions"; setTab: (v: "preview" | "edit" | "versions") => void; refreshShell: () => Promise<void>; refreshRun: (id: string) => Promise<RunView>; setError: (v: string) => void }) {
  const current = versions.find((version) => version.id === run.version_id) ?? versions[0];
  const [title, setTitle] = useState(current?.app_spec.hero_title ?? "");
  const [body, setBody] = useState(current?.app_spec.hero_body ?? "");
  const [color, setColor] = useState(current?.app_spec.primary_color ?? "#151515");
  const [publishing, setPublishing] = useState(false);
  const [deploymentUrl, setDeploymentUrl] = useState("");
  const [previewKey, setPreviewKey] = useState(0);
  useEffect(() => { if (current) { setTitle(current.app_spec.hero_title); setBody(current.app_spec.hero_body); setColor(current.app_spec.primary_color); } }, [current]);

  const save = async () => {
    try {
      const version = await api.revise(run.project_id, { hero_title: title, hero_body: body, primary_color: color });
      setVersions([version, ...versions]);
      await refreshRun(run.run_id);
      setPreviewKey((value) => value + 1);
      await refreshShell();
      setTab("preview");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Save failed"); }
  };
  const publish = async () => {
    if (!current) return;
    setPublishing(true);
    try {
      const deployment = await api.publish(run.project_id, current.id, "specify_version");
      setDeploymentUrl(deployment.public_url);
      await refreshShell();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Publish failed"); }
    finally { setPublishing(false); }
  };
  return <div className="result-view">
    <div className="result-toolbar">
      <div className="result-tabs"><button className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}><Monitor size={15} /> Preview</button><button className={tab === "edit" ? "active" : ""} onClick={() => setTab("edit")}><Code2 size={15} /> Edit</button><button className={tab === "versions" ? "active" : ""} onClick={() => setTab("versions")}><History size={15} /> Versions</button></div>
      <div className="toolbar-actions">
        {tab === "preview" && <div className="device-switch"><button className={device === "desktop" ? "active" : ""} onClick={() => setDevice("desktop")} aria-label="Desktop preview" title="Desktop preview"><Monitor size={16} /></button><button className={device === "mobile" ? "active" : ""} onClick={() => setDevice("mobile")} aria-label="Mobile preview" title="Mobile preview"><Smartphone size={16} /></button></div>}
        <button className="publish-button" onClick={publish} disabled={publishing}>{publishing ? <LoaderCircle className="spin" size={16} /> : <Rocket size={16} />} Publish</button>
      </div>
    </div>
    {deploymentUrl && <div className="published-banner"><Check size={16} /><span>Published successfully</span><a href={deploymentUrl} target="_blank" rel="noreferrer">Open public app <ExternalLink size={14} /></a></div>}
    {tab === "preview" && current && <div className="preview-stage"><div className={device === "mobile" ? "preview-frame mobile" : "preview-frame"}><iframe key={`${current.id}-${previewKey}`} src={`/preview/${current.id}`} title="Generated application preview" /></div></div>}
    {tab === "edit" && <div className="edit-panel"><div className="content-heading"><div><span>Structured edit</span><h1>Refine the current version</h1><p>Saving creates a new ProjectVersion and keeps the original.</p></div></div><label>Hero title<input value={title} onChange={(e) => setTitle(e.target.value)} /></label><label>Hero body<textarea value={body} onChange={(e) => setBody(e.target.value)} /></label><label>Primary color<div className="color-input"><input type="color" value={color} onChange={(e) => setColor(e.target.value)} /><input value={color} onChange={(e) => setColor(e.target.value)} /></div></label><button className="primary-action" onClick={save}><Check size={16} /> Save as new version</button></div>}
    {tab === "versions" && <div className="versions-panel"><div className="content-heading"><div><span>Project history</span><h1>Versions</h1><p>Restore always creates a new version; history is never overwritten.</p></div></div>{versions.map((version) => <div className="version-row" key={version.id}><span className="version-number">v{version.number}</span><div><strong>{version.summary}</strong><small>{new Date(version.created_at).toLocaleString()}</small></div>{version.id === run.version_id ? <b>Current</b> : <button onClick={async () => { const restored = await api.restore(run.project_id, version.id); setVersions([restored, ...versions]); await refreshRun(run.run_id); }}>Restore</button>}</div>)}</div>}
  </div>;
}

function StatusPill({ status }: { status: string }) { return <span className={`status-pill ${status}`}><i /> {status.replaceAll("_", " ")}</span>; }
function ModeBadge({ mode }: { mode: Mode }) { return <span className="mode-badge">{mode === "team" ? <Users size={14} /> : <Code2 size={14} />}{mode === "team" ? "Team pipeline" : "Engineer pipeline"}</span>; }
function SupportBadge({ level }: { level: string }) { return <span className={`support-badge ${level}`}>{level === "supported" ? <Check size={14} /> : <CircleAlert size={14} />}{level}</span>; }
