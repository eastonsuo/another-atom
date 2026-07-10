import type {
  AppSpec,
  AttachmentMeta,
  Blueprint,
  DeploymentView,
  Mode,
  ProjectView,
  QuotaView,
  RunEvent,
  RunView,
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
  createRun: (prompt: string, mode: Mode, attachments: AttachmentMeta[]) =>
    request<RunView>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ prompt, mode, attachments }),
    }),
  getRun: (runId: string) => request<RunView>(`/api/runs/${runId}`),
  latestRun: (projectId: string) => request<RunView>(`/api/projects/${projectId}/runs/latest`),
  approve: (runId: string, blueprint: Blueprint) =>
    request<RunView>(`/api/runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({ blueprint }),
    }),
  events: (runId: string) =>
    request<RunEvent[]>(`/api/runs/${runId}/events/history`),
  projects: () => request<ProjectView[]>("/api/projects"),
  quota: () => request<QuotaView>("/api/quota"),
  versions: (projectId: string) =>
    request<VersionView[]>(`/api/projects/${projectId}/versions`),
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
};
