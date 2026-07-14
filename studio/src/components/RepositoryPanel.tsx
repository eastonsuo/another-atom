import { Bug, Code2, Eye, FileJson, FileText, FolderGit2, GripVertical, LoaderCircle, Maximize2, Minimize2, Pencil, RefreshCw, Save, TerminalSquare, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import { api } from "../lib/api";
import type { ProjectFileContent, ProjectFileEntry, RunEvent, RunView, VersionView } from "../types";
import { MarkdownPreview } from "./MarkdownPreview";
import { TerminalPanel } from "./TerminalPanel";

type Language = "zh" | "en";
type ViewMode = "preview" | "source" | "edit";

const TOOL_PANEL_WIDTH_KEY = "another-atom-tool-panel-width";
const DEFAULT_TOOL_PANEL_WIDTH = 368;
const MIN_TOOL_PANEL_WIDTH = 320;

export function RepositoryPanel({ run, events, language, sandboxAvailable, logPanel, onVersionSaved, onError }: { run: RunView; events: RunEvent[]; language: Language; sandboxAvailable: boolean; logPanel: ReactNode; onVersionSaved: (version: VersionView) => void; onError: (message: string) => void }) {
  const [active, setActive] = useState<"files" | "terminal" | "logs" | null>(null);
  const [files, setFiles] = useState<ProjectFileEntry[]>([]);
  const [selected, setSelected] = useState<ProjectFileEntry | null>(null);
  const [fileContent, setFileContent] = useState<ProjectFileContent | null>(null);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState<ViewMode>("source");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [savedCommit, setSavedCommit] = useState("");
  const [panelWidth, setPanelWidth] = useState(() => {
    const saved = Number(window.localStorage.getItem(TOOL_PANEL_WIDTH_KEY));
    const preferred = Number.isFinite(saved) && saved >= MIN_TOOL_PANEL_WIDTH ? saved : DEFAULT_TOOL_PANEL_WIDTH;
    return Math.min(preferred, Math.max(MIN_TOOL_PANEL_WIDTH, window.innerWidth - 96));
  });
  const [fullScreen, setFullScreen] = useState(false);
  const dirty = mode === "edit" && fileContent !== null && draft !== fileContent.content;

  const confirmDiscard = useCallback(() => !dirty || window.confirm(copy(language, "Discard unsaved changes?")), [dirty, language]);

  const openFile = useCallback(async (file: ProjectFileEntry) => {
    if (!confirmDiscard()) return;
    setSelected(file);
    setError("");
    setSavedCommit("");
    try {
      const result = await api.projectFile(run.project_id, run.run_id, file.path, file.source);
      setFileContent(result);
      setDraft(result.content);
      setMode(result.render_mode === "markdown" ? "preview" : "source");
    } catch (reason) {
      setFileContent(null);
      setDraft("");
      setError(reason instanceof Error ? reason.message : copy(language, "Could not read file"));
    }
  }, [confirmDiscard, language, run.project_id, run.run_id]);

  const refresh = useCallback(async () => {
    if (!confirmDiscard()) return;
    setLoading(true);
    setError("");
    try {
      const next = await api.projectFiles(run.project_id, run.run_id);
      setFiles(next);
      const preferred = selected
        ? next.find((file) => file.source === selected.source && file.path === selected.path)
        : run.status === "awaiting_approval"
          ? next.find((file) => file.source === "repository" && file.path === "docs/product-spec.md")
            ?? next.find((file) => file.source === "repository" && file.path === "README.md")
          : next.find((file) => file.source === "repository" && file.path === "README.md")
          ?? next.find((file) => file.source === "artifact" && file.path.endsWith("app-spec.json"))
          ?? next[0];
      if (preferred) await openFile(preferred);
      else {
        setSelected(null);
        setFileContent(null);
        setDraft("");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(language, "Could not list files"));
    } finally {
      setLoading(false);
    }
  }, [confirmDiscard, language, openFile, run.project_id, run.run_id, run.status, selected]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
    // Refresh only when the Project/Run changes; selected file updates must not reload the panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.project_id, run.run_id, run.status]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  useEffect(() => {
    if (!fullScreen) return;
    const exit = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFullScreen(false);
    };
    window.addEventListener("keydown", exit);
    return () => window.removeEventListener("keydown", exit);
  }, [fullScreen]);

  const validationError = useMemo(() => {
    if (mode !== "edit" || fileContent?.kind !== "json") return "";
    try { JSON.parse(draft); return ""; }
    catch { return copy(language, "JSON is not valid"); }
  }, [draft, fileContent?.kind, language, mode]);

  const save = useCallback(async () => {
    if (!fileContent || !dirty || validationError) return;
    setSaving(true);
    setError("");
    try {
      const operationId = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const result = await api.saveProjectFile(run.project_id, fileContent.path, draft, fileContent.content_hash, operationId);
      setFileContent({ ...fileContent, content: draft, content_hash: result.content_hash });
      setFiles((current) => current.map((file) => file.source === "repository" && file.path === result.path ? { ...file, size: result.size } : file));
      setSavedCommit(result.git_commit.slice(0, 8));
      setMode(fileContent.render_mode === "markdown" ? "preview" : "source");
      if (result.version) onVersionSaved(result.version);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(language, "Could not save file"));
    } finally {
      setSaving(false);
    }
  }, [dirty, draft, fileContent, language, onVersionSaved, run.project_id, validationError]);

  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s" && mode === "edit") {
        event.preventDefault();
        void save();
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [mode, save]);

  const closePanel = () => {
    if (!confirmDiscard()) return;
    setFullScreen(false);
    setActive(null);
  };
  const activateTool = (tool: "files" | "terminal" | "logs") => {
    if (active === tool) { closePanel(); return; }
    if (active === "files" && !confirmDiscard()) return;
    setActive(tool);
  };
  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!active || fullScreen) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = panelWidth;
    const move = (moveEvent: PointerEvent) => {
      const maxWidth = Math.max(MIN_TOOL_PANEL_WIDTH, window.innerWidth - 96);
      const next = Math.min(maxWidth, Math.max(MIN_TOOL_PANEL_WIDTH, startWidth + startX - moveEvent.clientX));
      setPanelWidth(next);
      window.localStorage.setItem(TOOL_PANEL_WIDTH_KEY, String(Math.round(next)));
    };
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.classList.remove("resizing-tool-panel");
    };
    document.body.classList.add("resizing-tool-panel");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
    window.addEventListener("pointercancel", stop, { once: true });
  };
  const repositoryFiles = files.filter((file) => file.source === "repository");
  const artifactFiles = files.filter((file) => file.source === "artifact");

  return <aside className={active ? `workspace-tools open${fullScreen ? " fullscreen" : ""}` : "workspace-tools"} style={active && !fullScreen ? { width: `${panelWidth}px` } : undefined}>
    {active && !fullScreen && <div className="workspace-tool-resizer" role="separator" aria-orientation="vertical" aria-label={copy(language, "Resize panel")} onPointerDown={startResize}><GripVertical size={14} /></div>}
    <div className="workspace-tool-rail">
      <button className={active === "files" ? "active" : ""} onClick={() => activateTool("files")} title={copy(language, "Project files")}><FolderGit2 size={17} /><span>{copy(language, "Files")}</span></button>
      <button className={active === "terminal" ? "active" : ""} disabled={!run.version_id} onClick={() => activateTool("terminal")} title={!sandboxAvailable ? copy(language, "Sandbox Host is not configured") : run.version_id ? copy(language, "Restricted Vim") : copy(language, "Build a version before opening Vim")}><TerminalSquare size={17} /><span>Vim</span></button>
      <button className={active === "logs" ? "active" : ""} onClick={() => activateTool("logs")} title={copy(language, "Run log")}><Bug size={17} /><span>{copy(language, "Logs")}</span>{events.length > 0 && <b>{events.length}</b>}</button>
    </div>
    {active && <div className="workspace-tool-content">
      <div className="workspace-tool-actions">
        <button onClick={() => setFullScreen((current) => !current)} aria-label={copy(language, fullScreen ? "Exit full screen" : "Full screen")} title={copy(language, fullScreen ? "Exit full screen" : "Full screen")}>{fullScreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}</button>
        <button onClick={closePanel} aria-label={copy(language, "Close panel")} title={copy(language, "Close panel")}><X size={15} /></button>
      </div>
      {active === "files" ? <div className="repository-panel">
        <div className="repository-heading">
          <div><FolderGit2 size={17} /><span><strong>{copy(language, "Project files")}</strong><small>{copy(language, "Read and edit Project documents")}</small></span></div>
          <button onClick={() => void refresh()} disabled={loading || dirty} title={copy(language, "Refresh files")} aria-label={copy(language, "Refresh files")}>{loading ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}</button>
        </div>
        <div className="repository-tree">
          <FileGroup title={copy(language, "Project Repository")} files={repositoryFiles} selected={selected} onOpen={openFile} />
          <FileGroup title={copy(language, "Generated Artifacts")} files={artifactFiles} selected={selected} onOpen={openFile} />
        </div>
        <div className="repository-viewer">
          <div className="repository-viewer-head">
            <strong>{selected?.path ?? copy(language, "Select a file")}</strong>
            <div className="repository-file-actions">
              {selected?.source === "artifact" && <span>{copy(language, "Read-only artifact")}</span>}
              {selected?.source === "repository" && !selected.editable && <span>{copy(language, "Validated source")}</span>}
              {fileContent?.kind === "markdown" && mode !== "edit" && <><button className={mode === "preview" ? "active" : ""} onClick={() => setMode("preview")}><Eye size={12} />{copy(language, "Preview")}</button><button className={mode === "source" ? "active" : ""} onClick={() => setMode("source")}><Code2 size={12} />{copy(language, "Source")}</button></>}
              {fileContent?.editable && mode !== "edit" && <button onClick={() => { setDraft(fileContent.content); setMode("edit"); }}><Pencil size={12} />{copy(language, "Edit")}</button>}
            </div>
          </div>
          {error && <p className="repository-error">{error}</p>}
          {savedCommit && <p className="repository-saved">{copy(language, "Saved in commit")} <code>{savedCommit}</code></p>}
          {!error && fileContent && mode === "preview" ? <MarkdownPreview content={fileContent.content} /> : null}
          {!error && fileContent && mode === "source" ? <pre><code>{fileContent.content}</code></pre> : null}
          {!error && fileContent && mode === "edit" ? <div className="repository-editor">
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} aria-label={copy(language, "File content")} />
            <div><small className={dirty ? "dirty" : ""}>{dirty ? copy(language, "Unsaved changes") : copy(language, "No changes")}{validationError ? ` · ${validationError}` : ""}</small><span><button onClick={() => { setDraft(fileContent.content); setMode(fileContent.render_mode === "markdown" ? "preview" : "source"); }} disabled={saving}><Undo2 size={12} />{copy(language, "Cancel")}</button><button className="save" onClick={() => void save()} disabled={!dirty || saving || Boolean(validationError)}>{saving ? <LoaderCircle className="spin" size={12} /> : <Save size={12} />}{copy(language, saving ? "Saving" : "Save")}</button></span></div>
          </div> : null}
          {!error && !fileContent ? <p>{copy(language, "No generated files yet")}</p> : null}
        </div>
      </div> : active === "terminal" ? <div className="terminal-drawer">{sandboxAvailable ? <TerminalPanel projectId={run.project_id} language={language} onSaved={onVersionSaved} onError={onError} /> : <div className="sandbox-unavailable"><TerminalSquare size={28} /><strong>{copy(language, "Vim is not available")}</strong><p>{copy(language, "Configure a separate Sandbox Host before opening the restricted editor. The Control Plane will not run file tools directly.")}</p></div>}</div> : logPanel}
    </div>}
  </aside>;
}

function FileGroup({ title, files, selected, onOpen }: { title: string; files: ProjectFileEntry[]; selected: ProjectFileEntry | null; onOpen: (file: ProjectFileEntry) => Promise<void> }) {
  return <section><strong>{title}<span>{files.length}</span></strong>{files.length === 0 ? <small>—</small> : files.map((file) => {
    const active = selected?.path === file.path && selected.source === file.source;
    const depth = Math.min(file.path.split("/").length - 1, 3);
    return <button className={active ? "active" : ""} style={{ paddingLeft: `${10 + depth * 12}px` }} onClick={() => void onOpen(file)} key={`${file.source}:${file.path}`} title={file.path}>{file.kind === "json" ? <FileJson size={13} /> : <FileText size={13} />}<span>{file.path.split("/").at(-1)}</span><small>{formatSize(file.size)}</small></button>;
  })}</section>;
}

function formatSize(bytes: number): string { return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`; }

function copy(language: Language, text: string): string {
  if (language === "en") return text;
  return {
    "Project files": "项目文件", "Files": "文件", "Restricted Vim": "受限 Vim", "Build a version before opening Vim": "生成项目版本后才能打开 Vim", "Sandbox Host is not configured": "当前未配置 Sandbox Host，Vim 不可用", "Vim is not available": "当前无法打开 Vim", "Configure a separate Sandbox Host before opening the restricted editor. The Control Plane will not run file tools directly.": "需要先配置独立 Sandbox Host 才能使用受限编辑器；Control Plane 不会直接执行文件工具。", "Run log": "运行日志", "Logs": "日志", "Close panel": "关闭面板", "Resize panel": "拖动调整面板宽度", "Full screen": "全屏查看", "Exit full screen": "退出全屏", "Read and edit Project documents": "查看和编辑项目文档", "Refresh files": "刷新文件", "Project Repository": "项目代码库", "Generated Artifacts": "本次生成产物", "Read-only artifact": "只读产物", "Validated source": "受控源码", "Select a file": "选择文件查看内容", "No generated files yet": "暂时没有可查看的文件", "Could not list files": "无法获取文件列表", "Could not read file": "无法读取文件", "Could not save file": "无法保存文件", "Discard unsaved changes?": "当前文件有未保存修改，确定放弃吗？", "Preview": "预览", "Source": "源码", "Edit": "编辑", "File content": "文件内容", "Unsaved changes": "未保存", "No changes": "没有修改", "JSON is not valid": "JSON 格式不正确", "Cancel": "取消", "Save": "保存", "Saving": "保存中", "Saved in commit": "已保存到提交",
  }[text] ?? text;
}
