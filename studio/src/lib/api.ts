import type {
  AppSpec,
  AttachmentMeta,
  Blueprint,
  DeploymentView,
  Mode,
  ModelsView,
  ProjectFileContent,
  ProjectFileEntry,
  ProjectView,
  QuotaView,
  RunEvent,
  RunView,
  LeadDecisionView,
  SandboxSessionView,
  UserView,
  VersionView,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(error.message ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<UserView>("/api/auth/me"),
  signup: (username: string, password: string, displayName?: string) =>
    request<UserView>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ username, password, display_name: displayName || undefined }),
    }),
  login: (username: string, password: string) =>
    request<UserView>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  leadMessage: (message: string, model: string, forceTeam = false) =>
    request<LeadDecisionView>("/api/lead/messages", {
      method: "POST",
      body: JSON.stringify({ message, model, force_team: forceTeam }),
    }),
  createRun: (prompt: string, mode: Mode, model: string, attachments: AttachmentMeta[]) =>
    request<RunView>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ prompt, mode, model, attachments }),
    }),
  getRun: (runId: string) => request<RunView>(`/api/runs/${runId}`),
  latestRun: (projectId: string) => request<RunView>(`/api/projects/${projectId}/runs/latest`),
  approve: (runId: string, blueprint: Blueprint) =>
    request<RunView>(`/api/runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({ blueprint }),
    }),
  confirmAlternative: (runId: string, prompt: string) =>
    request<RunView>(`/api/runs/${runId}/confirm-alternative`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  regenerateAlternative: (runId: string, prompt: string) =>
    request<RunView>(`/api/runs/${runId}/regenerate-alternative`, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  events: (runId: string) =>
    request<RunEvent[]>(`/api/runs/${runId}/events/history`),
  downloadRunLog: (runId: string) => `/api/runs/${runId}/logs/download`,
  projects: () => request<ProjectView[]>("/api/projects"),
  quota: () => request<QuotaView>("/api/quota"),
  models: () => request<ModelsView>("/api/models"),
  versions: (projectId: string) =>
    request<VersionView[]>(`/api/projects/${projectId}/versions`),
  projectFiles: (projectId: string, runId: string) =>
    request<ProjectFileEntry[]>(`/api/projects/${projectId}/files?${new URLSearchParams({ run_id: runId })}`),
  projectFile: (projectId: string, runId: string, path: string, source: ProjectFileEntry["source"]) =>
    request<ProjectFileContent>(`/api/projects/${projectId}/files/content?${new URLSearchParams({ run_id: runId, path, source })}`),
  preview: (versionId: string) => request<AppSpec>(`/api/previews/${versionId}`),
  publicApp: (publicId: string) => request<AppSpec>(`/api/public/${publicId}`),
  revise: (projectId: string, revision: Partial<AppSpec>) =>
    request<VersionView>(`/api/projects/${projectId}/revisions`, {
      method: "POST",
      body: JSON.stringify(revision),
    }),
  restore: (projectId: string, versionId: string) =>
    request<VersionView>(`/api/projects/${projectId}/restore/${versionId}`, {
      method: "POST",
    }),
  publish: (projectId: string, versionId: string, strategy: string) =>
    request<DeploymentView>(`/api/projects/${projectId}/publish`, {
      method: "POST",
      body: JSON.stringify({ version_id: versionId, strategy }),
    }),
  unpublish: (projectId: string) =>
    request<void>(`/api/projects/${projectId}/unpublish`, { method: "POST" }),
  openSandbox: (projectId: string, signal?: AbortSignal) =>
    request<SandboxSessionView>(`/api/projects/${projectId}/sandbox/sessions`, {
      method: "POST",
      signal,
    }),
  closeSandbox: (projectId: string, sessionId: string) =>
    request<void>(`/api/projects/${projectId}/sandbox/sessions/${sessionId}`, {
      method: "DELETE",
    }),
  saveSandbox: (projectId: string, sessionId: string) =>
    request<VersionView>(`/api/projects/${projectId}/sandbox/sessions/${sessionId}/save`, {
      method: "POST",
    }),
};
