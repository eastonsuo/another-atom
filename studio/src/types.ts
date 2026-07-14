export type Mode = "engineer" | "team";
export type SupportLevel = "supported" | "adapted" | "unsupported";
export type WorkspaceTab = "preview" | "edit" | "code" | "versions";

export interface AttachmentMeta {
  name: string;
  size: number;
  content_type: string;
}

export interface Blueprint {
  schema_version: "1.0";
  project_name: string;
  product_type: string;
  support_level: SupportLevel;
  support_reasons: string[];
  mapped_requirements: string[];
  omitted_requirements: string[];
  rewrite_suggestion: string | null;
  capability_policy_version: "catalog-v1" | "web-v1";
  pages: string[];
  modules: string[];
  visual_direction: string;
  data_requirements: string[];
}

export interface ProductSpec {
  schema_version: "1.0";
  path: "docs/product-spec.md";
  summary: string;
  content: string;
  content_hash: string;
}

export interface ProductItem {
  id: string;
  name: string;
  category: string;
  price: string;
  description: string;
  image_url: string;
}

export interface AppSpec {
  schema_version: "1.0";
  project_name: string;
  tagline: string;
  hero_title: string;
  hero_body: string;
  primary_color: string;
  accent_color: string;
  background_color: string;
  pages: { route: string; name: string; sections: string[] }[];
  products: ProductItem[];
  html: string;
  css: string;
  javascript: string;
}

export interface RunView {
  run_id: string;
  project_id: string;
  session_id: string;
  prompt: string;
  mode: Mode;
  model: string;
  trigger: "build" | "ai_edit";
  base_version_id: string | null;
  status: string;
  current_stage: string;
  blueprint: Blueprint | null;
  product_spec: ProductSpec | null;
  app_spec: AppSpec | null;
  validation_report: { passed: boolean; checks: { check_id: string; label: string; status: string; detail?: string | null }[] } | null;
  architecture_spec: {
    architecture_summary: string;
    page_strategy: string[];
    data_entities: string[];
  } | null;
  data_profile: { summary: string; entities: string[]; insights: string[]; warnings: string[] } | null;
  review_report: { summary: string; verdict: "accept" | "rework" | "needs_input"; warnings: string[]; suggested_actions: string[] } | null;
  build_job_id: string | null;
  version_id: string | null;
  error_code: string | null;
  error_message: string | null;
  pending_human_task: HumanTaskView | null;
}

export interface HumanTaskView {
  id: string;
  project_id: string;
  run_id: string;
  kind: "input_request" | "approval";
  status: "pending" | "answered" | "approved" | "rejected" | "cancelled" | "stale";
  stage: string;
  prompt: string;
  payload: Record<string, unknown>;
  response: Record<string, unknown> | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ProjectMessageView {
  id: string;
  project_id: string;
  run_id: string | null;
  role: "user" | "lead" | "system";
  message_type: "request" | "answer" | "clarification" | "clarification_response" | "change_proposal" | "change_brief" | "result" | "error";
  content: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ProjectMessageResult {
  intent: "answer" | "clarify" | "propose_change";
  user_message: ProjectMessageView;
  lead_message: ProjectMessageView;
  proposal_id: string | null;
  model: string;
  fallback_provider: string | null;
}

export interface RunEvent {
  event_id: string;
  sequence: number;
  run_id: string;
  type: string;
  payload: { message: string; stage?: string; [key: string]: unknown };
  timestamp: string;
}

export interface VersionView {
  id: string;
  project_id: string;
  number: number;
  source: string;
  summary: string;
  app_spec: AppSpec;
  created_at: string;
  git_commit: string | null;
}

export interface DeploymentView {
  public_id: string;
  project_id: string;
  version_id: string;
  strategy: "always_latest" | "specify_version";
  status: "live" | "paused";
  public_url: string;
}

export interface ProjectView {
  id: string;
  name: string;
  status: string;
  support_level: SupportLevel | null;
  current_version_id: string | null;
  deployment: DeploymentView | null;
  created_at: string;
  updated_at: string;
  repository_ready: boolean;
  repository_branch: string;
}

export interface ProjectFileEntry {
  path: string;
  source: "repository" | "artifact";
  size: number;
  kind: "markdown" | "json" | "code" | "text";
  text: boolean;
  editable: boolean;
  render_mode: "markdown" | "source";
}

export interface ProjectFileContent {
  path: string;
  source: "repository" | "artifact";
  content: string;
  content_hash: string;
  editable: boolean;
  kind: "markdown" | "json" | "code" | "text";
  render_mode: "markdown" | "source";
}

export interface ProjectFileSaveResult {
  path: string;
  content_hash: string;
  size: number;
  git_commit: string;
  version: VersionView | null;
  saved_at: string;
}

export interface QuotaView {
  limit: number;
  used: number;
  reserved: number;
  remaining: number;
}

export interface ModelsView {
  provider: string;
  fallback_provider: string | null;
  sandbox_available: boolean;
  default_model: string;
  models: { id: string; label: string; usage: "medium" | "extra_high" | "local" }[];
}

export interface UserView {
  id: string;
  username: string;
  display_name: string;
  role: "user" | "admin";
}

export interface LeadDecisionView {
  message_id: string;
  route: "direct" | "clarify" | "team";
  response: string;
  reason: string;
  clarification_questions: LeadClarificationQuestion[];
  model: string;
  fallback_provider: string | null;
}

export interface LeadClarificationQuestion {
  id: string;
  question: string;
  options: LeadClarificationOption[];
}

export interface LeadClarificationOption {
  value: string;
  label: string;
  description: string | null;
}

export interface SandboxSessionView {
  session_id: string;
  project_id: string;
  websocket_path: string;
  expires_at: string;
}

export interface AdminUserView extends UserView {
  role: "admin";
}

export interface AdminUserSummary {
  id: string;
  username: string;
  display_name: string;
  plan: string;
  quota_limit: number;
  quota_used: number;
  quota_reserved: number;
  project_count: number;
  created_at: string;
}

export interface AdminUserList {
  items: AdminUserSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminRunSummary {
  id: string;
  model: string;
  status: string;
  current_stage: string;
  error_code: string | null;
  error_summary: string | null;
  quota_spent: number;
  created_at: string;
  updated_at: string;
}

export interface AdminProjectSummary {
  id: string;
  name: string;
  summary: string;
  status: string;
  updated_at: string;
  support_level: string | null;
  latest_run: AdminRunSummary | null;
}

export interface AdminProjectList {
  items: AdminProjectSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface AdminProjectDetail {
  project: AdminProjectSummary;
  prompt_summary: string;
  events: RunEvent[];
}
