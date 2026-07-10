export type Mode = "engineer" | "team";
export type SupportLevel = "supported" | "adapted" | "unsupported";

export interface AttachmentMeta {
  name: string;
  size: number;
  content_type: string;
}

export interface Blueprint {
  schema_version: "1.0";
  project_name: string;
  product_type: "product_catalog";
  support_level: SupportLevel;
  support_reasons: string[];
  mapped_requirements: string[];
  omitted_requirements: string[];
  rewrite_suggestion: string | null;
  capability_policy_version: "catalog-v1";
  pages: string[];
  modules: string[];
  visual_direction: string;
  data_requirements: string[];
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
}

export interface RunView {
  run_id: string;
  project_id: string;
  session_id: string;
  mode: Mode;
  status: string;
  current_stage: string;
  blueprint: Blueprint | null;
  app_spec: AppSpec | null;
  validation_report: { passed: boolean; checks: { label: string; status: string }[] } | null;
  qa_review: { summary: string; warnings: string[]; suggested_actions: string[] } | null;
  build_job_id: string | null;
  version_id: string | null;
  error_code: string | null;
  error_message: string | null;
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
}

export interface QuotaView {
  limit: number;
  used: number;
  reserved: number;
  remaining: number;
}
