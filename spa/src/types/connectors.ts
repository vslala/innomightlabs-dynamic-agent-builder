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

export type MCPAuthType = "api_key" | "oauth";
export type MCPTransport = "streamable_http";

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
  server_url: string;
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
}

export interface AgentMCPConnection {
  agent_id: string;
  mcp_id: string;
  name: string;
  server_url: string;
  enabled: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface CreateMCPConnectionRequest {
  name: string;
  server_url: string;
  auth_type: MCPAuthType;
  api_key?: MCPApiKeyAuthConfig;
  oauth?: MCPOAuthProviderConfig;
  enabled: boolean;
}

export interface UpdateMCPConnectionRequest {
  name?: string;
  server_url?: string;
  auth_type?: MCPAuthType;
  api_key?: MCPApiKeyAuthConfig;
  oauth?: MCPOAuthProviderConfig;
  enabled?: boolean;
}

export interface UpdateAgentMCPConnectionRequest {
  enabled: boolean;
}
