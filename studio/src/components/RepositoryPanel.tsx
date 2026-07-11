import { FileJson, FileText, FolderGit2, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ProjectFileEntry, RunView } from "../types";

type Language = "zh" | "en";

export function RepositoryPanel({ run, language }: { run: RunView; language: Language }) {
  const [files, setFiles] = useState<ProjectFileEntry[]>([]);
  const [selected, setSelected] = useState<ProjectFileEntry | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const openFile = useCallback(async (file: ProjectFileEntry) => {
    setSelected(file);
    setError("");
    try {
      const result = await api.projectFile(run.project_id, run.run_id, file.path, file.source);
      setContent(result.content);
    } catch (reason) {
      setContent("");
      setError(reason instanceof Error ? reason.message : copy(language, "Could not read file"));
    }
  }, [language, run.project_id, run.run_id]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await api.projectFiles(run.project_id, run.run_id);
      setFiles(next);
      const preferred = next.find((file) => file.source === "artifact" && file.path.endsWith("app-spec.json"))
        ?? next.find((file) => file.source === "repository" && file.path === "app-spec.json")
        ?? next[0];
      if (preferred) await openFile(preferred);
      else {
        setSelected(null);
        setContent("");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : copy(language, "Could not list files"));
    } finally {
      setLoading(false);
    }
  }, [language, openFile, run.project_id, run.run_id]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const repositoryFiles = files.filter((file) => file.source === "repository");
  const artifactFiles = files.filter((file) => file.source === "artifact");

  return <aside className="repository-panel">
    <div className="repository-heading">
      <div><FolderGit2 size={17} /><span><strong>{copy(language, "Project files")}</strong><small>{copy(language, "Live HTTP file list")}</small></span></div>
      <button onClick={() => void refresh()} disabled={loading} title={copy(language, "Refresh files")} aria-label={copy(language, "Refresh files")}>
        {loading ? <LoaderCircle className="spin" size={15} /> : <RefreshCw size={15} />}
      </button>
    </div>
    <div className="repository-tree">
      <FileGroup title={copy(language, "Project Repository")} files={repositoryFiles} selected={selected} onOpen={openFile} />
      <FileGroup title={copy(language, "Generated Artifacts")} files={artifactFiles} selected={selected} onOpen={openFile} />
    </div>
    <div className="repository-viewer">
      <div><strong>{selected?.path ?? copy(language, "Select a file")}</strong>{selected?.source === "artifact" && <span>{copy(language, "Not committed")}</span>}</div>
      {error ? <p>{error}</p> : selected ? <pre><code>{content}</code></pre> : <p>{copy(language, "No generated files yet")}</p>}
    </div>
  </aside>;
}

function FileGroup({ title, files, selected, onOpen }: { title: string; files: ProjectFileEntry[]; selected: ProjectFileEntry | null; onOpen: (file: ProjectFileEntry) => Promise<void> }) {
  return <section>
    <strong>{title}<span>{files.length}</span></strong>
    {files.length === 0 ? <small>—</small> : files.map((file) => {
      const active = selected?.path === file.path && selected.source === file.source;
      const depth = Math.min(file.path.split("/").length - 1, 3);
      return <button className={active ? "active" : ""} style={{ paddingLeft: `${10 + depth * 12}px` }} onClick={() => void onOpen(file)} key={`${file.source}:${file.path}`} title={file.path}>
        {file.path.endsWith(".json") ? <FileJson size={13} /> : <FileText size={13} />}
        <span>{file.path.split("/").at(-1)}</span>
        <small>{formatSize(file.size)}</small>
      </button>;
    })}
  </section>;
}

function formatSize(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

function copy(language: Language, text: string): string {
  if (language === "en") return text;
  return {
    "Project files": "项目文件",
    "Live HTTP file list": "后台实时文件列表",
    "Refresh files": "刷新文件",
    "Project Repository": "项目代码库",
    "Generated Artifacts": "本次生成产物",
    "Not committed": "尚未提交",
    "Select a file": "选择文件查看内容",
    "No generated files yet": "暂时没有可查看的文件",
    "Could not list files": "无法获取文件列表",
    "Could not read file": "无法读取文件",
  }[text] ?? text;
}
