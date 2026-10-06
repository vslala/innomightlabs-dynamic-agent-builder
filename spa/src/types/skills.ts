import type { FormSchema } from "./form";

export type SkillConfigValue = string | Record<string, string>;
export type SkillConfig = Record<string, SkillConfigValue>;

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
  repeatable: boolean;
  /** The skill uses the owner's own accounts or machine, so it can never be shared once installed. */
  owner_only: boolean;
}

export interface InstalledSkill {
  installed_skill_id: string;
  skill_id: string;
  namespace: string;
  name: string;
  description: string;
  enabled: boolean;
  installed_at: string;
  updated_at: string | null;
  config: SkillConfig;
  secret_fields: string[];
  requires_oauth: boolean;
  oauth_provider_name: string | null;
  available_to: SkillActorKind[];
  /** The skill uses the owner's own accounts or credentials, so nobody else can be given it. */
  owner_only: boolean;
}

/** Who is chatting with the agent: its owner, a /v1 secret key, an A2A caller, or a widget visitor. */
export type SkillActorKind = "owner" | "api" | "a2a" | "visitor";

export interface SkillInstallRequest {
  config: SkillConfig;
}

export interface SkillUpdateRequest {
  enabled?: boolean;
  config?: SkillConfig;
  available_to?: SkillActorKind[];
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

export interface A2ARemoteOAuthStartRequest {
  agent_id: string;
  installed_skill_id: string;
  service_url?: string | null;
  target_origin?: string | null;
  return_to: string;
}

export type A2ARemoteOAuthStartResponse = SkillOAuthStartResponse;
