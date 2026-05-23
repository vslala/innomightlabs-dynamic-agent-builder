import type { FormSchema } from "./form";

export interface SkillConnectorStatus {
  connector_id: string;
  provider_name: string;
  required: boolean;
  connected: boolean;
  connect_path: string | null;
}

export interface SkillCatalogItem {
  skill_id: string;
  namespace: string;
  name: string;
  description: string;
  action_names: string[];
  has_form: boolean;
  requires_oauth: boolean;
  oauth_provider_name: string | null;
  oauth_connected: boolean | null;
  oauth_start_path: string | null;
  connectors: SkillConnectorStatus[];
  available: boolean;
}

export interface InstalledSkill {
  skill_id: string;
  namespace: string;
  name: string;
  description: string;
  enabled: boolean;
  installed_at: string;
  updated_at: string | null;
  config: Record<string, string>;
  secret_fields: string[];
  requires_oauth: boolean;
  oauth_provider_name: string | null;
}

export interface SkillInstallRequest {
  config: Record<string, string>;
}

export interface SkillUpdateRequest {
  enabled?: boolean;
  config?: Record<string, string>;
}

export type SkillInstallSchema = FormSchema;

export interface SkillOAuthStartRequest {
  agent_id: string;
  skill_id: string;
  return_to: string;
}

export interface SkillOAuthStartResponse {
  authorize_url: string;
}

export type GoogleDriveOAuthStartRequest = SkillOAuthStartRequest;
export type GoogleDriveOAuthStartResponse = SkillOAuthStartResponse;
