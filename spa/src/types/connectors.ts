import type { SkillActorKind } from "./skills";

export interface ConnectorStatus {
  connector_id: string;
  provider_name: string;
  display_name: string;
  connected: boolean;
  connect_path: string;
  icon: string;
}

export interface ConnectorStartRequest {
  return_to: string;
}

export interface ConnectorStartResponse {
  authorize_url: string;
}

export type MCPAuthType = "none" | "api_key" | "oauth";
export type MCPTransport = "streamable_http" | "stdio";
export type MCPSetupState = "needs_input" | "needs_sign_in" | "ready";
export type MCPRuntimeState = "starting" | "running" | "failed" | "stopped";
export type MCPOAuthDeliveryKind = "access_token_env" | "google_authorized_user_file";

export interface MCPApiKeyAuthConfig {
  headers: MCPAuthHeader[];
}

export interface MCPOAuthProviderConfig {
  authorization_url: string;
  token_url: string;
  client_id: string;
  client_secret?: string;
  scope?: string;
  resource_url?: string;
}

export interface MCPOAuthDiscoveryRequest {
  server_url?: string;
  issuer_url?: string;
}

export interface MCPOAuthDiscoveryResponse {
  authorization_url: string;
  token_url: string;
  client_id: string;
  client_secret: string;
  scope: string;
  resource_url: string;
  authorization_server: string;
  registration_endpoint?: string | null;
  registered_client: boolean;
  client_registration: "manual" | "dynamic";
}

export interface MCPStdioEnvVar {
  name: string;
  value: string;
  kind: "value" | "file";
  secret: boolean;
}

export interface MCPStdioConfig {
  package: string;
  args: string[];
  env: MCPStdioEnvVar[];
}

export interface MCPStdioEnvSummary {
  name: string;
  kind: "value" | "file";
  secret: boolean;
  value?: string | null;
}

export interface MCPStdioSummary {
  package: string;
  args: string[];
  env: MCPStdioEnvSummary[];
}

export interface MCPOAuthDelivery {
  kind: MCPOAuthDeliveryKind;
  env_name: string;
}

export interface MCPStdioPackage {
  key: string;
  entrypoint: string;
  installed: boolean;
}

export interface MCPRuntimeStatus {
  state: MCPRuntimeState;
  package?: string;
  started_at?: string | null;
  last_used_at?: string | null;
  exit_code?: number | null;
  error?: string | null;
  stderr_tail: string;
  server_info?: Record<string, unknown> | null;
}

export interface MCPProvider {
  key: string;
  display_name: string;
  description: string;
  icon: string;
  docs_url: string;
  transport: MCPTransport;
  has_inputs: boolean;
  has_sign_in: boolean;
  installed_count: number;
}

export interface MCPProviderInstallRequest {
  inputs: Record<string, string>;
  name?: string;
  return_to: string;
}

export interface MCPProviderInstallResponse {
  connection: MCPConnection;
  authorize_url?: string | null;
}

export interface MCPAuthHeader {
  name: string;
  value: string;
}

export interface MCPConnection {
  mcp_id: string;
  name: string;
  server_url: string;
  transport: MCPTransport;
  auth_type: MCPAuthType;
  oauth_connected: boolean;
  enabled: boolean;
  created_at: string;
  updated_at?: string | null;
  provider_key?: string | null;
  setup_state: MCPSetupState;
  inputs: Record<string, string>;
  stdio?: MCPStdioSummary | null;
  oauth_delivery?: MCPOAuthDelivery | null;
}

export interface AgentMCPConnection {
  agent_id: string;
  mcp_id: string;
  name: string;
  server_url: string;
  enabled: boolean;
  sharing: MCPSharingSummary;
  created_at: string;
  updated_at?: string | null;
}

/** Anyone an owner can share a connector with. The owner always has every connector. */
export type MCPAudience = Exclude<SkillActorKind, "owner">;

export interface MCPSharingSummary {
  available_to: MCPAudience[];
  allowed_tool_count: number;
  consent_outdated: boolean;
}

export interface MCPSharingConsent {
  accepted_by: string;
  accepted_at: string;
  version: string;
}

export interface MCPSharing {
  available_to: MCPAudience[];
  allowed_tools: string[];
  consent?: MCPSharingConsent | null;
}

export interface MCPCatalogTool {
  name: string;
  title?: string | null;
  description: string;
  read_only: boolean;
  destructive: boolean;
}

export interface MCPToolCatalog {
  tools: MCPCatalogTool[];
  fetched_at: string;
}

export interface MCPSharingView {
  agent_id: string;
  mcp_id: string;
  connection_name: string;
  sharing: MCPSharing;
  catalog?: MCPToolCatalog | null;
  catalog_error?: string | null;
  disclaimer: { version: string; paragraphs: string[] };
}

export interface UpdateMCPSharingRequest {
  available_to: MCPAudience[];
  allowed_tools: string[];
  accept_disclaimer_version?: string;
}

export interface CreateMCPConnectionRequest {
  name: string;
  transport?: MCPTransport;
  server_url?: string;
  auth_type: MCPAuthType;
  api_key?: MCPApiKeyAuthConfig;
  oauth?: MCPOAuthProviderConfig;
  stdio?: MCPStdioConfig;
  oauth_delivery?: MCPOAuthDelivery;
  enabled: boolean;
}

export interface UpdateMCPConnectionRequest {
  name?: string;
  server_url?: string;
  auth_type?: MCPAuthType;
  api_key?: MCPApiKeyAuthConfig;
  oauth?: MCPOAuthProviderConfig;
  stdio?: MCPStdioConfig;
  oauth_delivery?: MCPOAuthDelivery;
  enabled?: boolean;
  inputs?: Record<string, string>;
}

export interface UpdateAgentMCPConnectionRequest {
  enabled: boolean;
}
