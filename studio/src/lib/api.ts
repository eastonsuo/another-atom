import type {
  AppSpec,
  AdminProjectDetail,
  AdminProjectList,
  AdminUserList,
  AdminUserView,
  AttachmentMeta,
  Blueprint,
  DeploymentView,
  Mode,
  ModelsView,
  ProjectFileContent,
  ProjectFileEntry,
  ProjectFileSaveResult,
  ProjectMessageView,
  ProjectMessageResult,
  HumanTaskView,
  ProjectView,
  QuotaView,
  RunEvent,
  RunView,
  LeadDecisionView,
  SandboxSessionView,
  UserView,
  VersionView,
} from "../types";

export class ApiError extends Error {
  constructor(public readonly code: string, message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: response.statusText }));
    throw new ApiError(error.code ?? "REQUEST_FAILED", error.message ?? "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  adminLogin: (username: string, password: string) =>
    request<AdminUserView>("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  adminMe: () => request<AdminUserView>("/api/admin/me"),
  adminUsers: (query = "", page = 1, pageSize = 20) =>
    request<AdminUserList>(`/api/admin/users?${new URLSearchParams({ query, page: String(page), page_size: String(pageSize) })}`),
  adminPromoteUser: (userId: string) =>
    request<AdminUserView>(`/api/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role: "admin" }),
    }),
  adminUserProjects: (userId: string, page = 1, pageSize = 20) =>
    request<AdminProjectList>(`/api/admin/users/${userId}/projects?${new URLSearchParams({ page: String(page), page_size: String(pageSize) })}`),
  adminProject: (projectId: string) =>
    request<AdminProjectDetail>(`/api/admin/projects/${projectId}`),
  adminRunLog: (runId: string) => `/api/admin/runs/${runId}/logs/download`,
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
  projectMessages: (projectId: string) =>
    request<ProjectMessageView[]>(`/api/projects/${projectId}/messages`),
  sendProjectMessage: (projectId: string, message: string, model: string) =>
    request<ProjectMessageResult>(`/api/projects/${projectId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message, model }),
    }),
  approveProjectChange: (projectId: string, proposalId: string) =>
    request<RunView>(`/api/projects/${projectId}/change-proposals/${proposalId}/approve`, {
      method: "POST",
    }),
  humanTasks: (runId: string) =>
    request<HumanTaskView[]>(`/api/runs/${runId}/human-tasks`),
  respondHumanTask: (taskId: string, response: string) =>
    request<RunView>(`/api/human-tasks/${taskId}/respond`, {
      method: "POST",
      body: JSON.stringify({ response }),
    }),
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
  updateProductSpec: (runId: string, summary: string | null, action: "save" | "regenerate", instruction?: string) =>
    request<RunView>(`/api/runs/${runId}/product-spec`, {
      method: "POST",
      body: JSON.stringify({ summary, action, instruction }),
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
  saveProjectFile: (projectId: string, path: string, content: string, expectedContentHash: string, operationId: string) =>
    request<ProjectFileSaveResult>(`/api/projects/${projectId}/files/content`, {
      method: "PUT",
      body: JSON.stringify({ path, content, expected_content_hash: expectedContentHash, operation_id: operationId }),
    }),
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
