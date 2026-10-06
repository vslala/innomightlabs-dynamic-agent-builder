import { httpClient } from "../http/client";
import type {
  ConnectorStartRequest,
  ConnectorStartResponse,
  ConnectorStatus,
  AgentMCPConnection,
  CreateMCPConnectionRequest,
  MCPConnection,
  MCPOAuthDiscoveryRequest,
  MCPOAuthDiscoveryResponse,
  MCPProvider,
  MCPProviderInstallRequest,
  MCPProviderInstallResponse,
  MCPRuntimeStatus,
  MCPSharingView,
  MCPStdioPackage,
  MCPToolCatalog,
  UpdateAgentMCPConnectionRequest,
  UpdateMCPConnectionRequest,
  UpdateMCPSharingRequest,
} from "../../types/connectors";
import type { FormSchema } from "../../types/form";

class ConnectorApiService {
  async listConnectors(): Promise<ConnectorStatus[]> {
    return httpClient.get<ConnectorStatus[]>("/connectors");
  }

  async startConnector(path: string, payload: ConnectorStartRequest): Promise<ConnectorStartResponse> {
    return httpClient.post<ConnectorStartResponse>(path, payload);
  }

  async listMCPConnections(): Promise<MCPConnection[]> {
    return httpClient.get<MCPConnection[]>("/connectors/mcp");
  }

  async createMCPConnection(payload: CreateMCPConnectionRequest): Promise<MCPConnection> {
    return httpClient.post<MCPConnection>("/connectors/mcp", payload);
  }

  async updateMCPConnection(mcpId: string, payload: UpdateMCPConnectionRequest): Promise<MCPConnection> {
    return httpClient.patch<MCPConnection>(`/connectors/mcp/${mcpId}`, payload);
  }

  async deleteMCPConnection(mcpId: string): Promise<void> {
    await httpClient.delete<void>(`/connectors/mcp/${mcpId}`);
  }

  async startMCPOAuth(mcpId: string, payload: ConnectorStartRequest): Promise<ConnectorStartResponse> {
    return httpClient.post<ConnectorStartResponse>(`/connectors/mcp/${mcpId}/oauth/start`, payload);
  }

  async discoverMCPOAuth(payload: MCPOAuthDiscoveryRequest): Promise<MCPOAuthDiscoveryResponse> {
    return httpClient.post<MCPOAuthDiscoveryResponse>("/connectors/mcp/oauth/discover", payload);
  }

  async listMCPProviders(): Promise<MCPProvider[]> {
    return httpClient.get<MCPProvider[]>("/connectors/mcp/providers");
  }

  async getMCPProviderInstallForm(key: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(`/connectors/mcp/providers/${key}/forms/install`);
  }

  async installMCPProvider(key: string, payload: MCPProviderInstallRequest): Promise<MCPProviderInstallResponse> {
    return httpClient.post<MCPProviderInstallResponse>(`/connectors/mcp/providers/${key}/install`, payload);
  }

  async getMCPConnectionSettingsForm(mcpId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(`/connectors/mcp/${mcpId}/forms/settings`);
  }

  async listMCPStdioPackages(): Promise<MCPStdioPackage[]> {
    return httpClient.get<MCPStdioPackage[]>("/connectors/mcp/stdio/packages");
  }

  async getMCPRuntime(mcpId: string): Promise<MCPRuntimeStatus> {
    return httpClient.get<MCPRuntimeStatus>(`/connectors/mcp/${mcpId}/runtime`);
  }

  async restartMCPRuntime(mcpId: string): Promise<MCPRuntimeStatus> {
    return httpClient.post<MCPRuntimeStatus>(`/connectors/mcp/${mcpId}/runtime/restart`, {});
  }

  async listAgentMCPConnections(agentId: string): Promise<AgentMCPConnection[]> {
    return httpClient.get<AgentMCPConnection[]>(`/agents/${agentId}/mcp-connections`);
  }

  async updateAgentMCPConnection(
    agentId: string,
    mcpId: string,
    payload: UpdateAgentMCPConnectionRequest
  ): Promise<AgentMCPConnection> {
    return httpClient.put<AgentMCPConnection>(`/agents/${agentId}/mcp-connections/${mcpId}`, payload);
  }

  async deleteAgentMCPConnection(agentId: string, mcpId: string): Promise<void> {
    await httpClient.delete<void>(`/agents/${agentId}/mcp-connections/${mcpId}`);
  }

  async getAgentMCPSharing(agentId: string, mcpId: string): Promise<MCPSharingView> {
    return httpClient.get<MCPSharingView>(`/agents/${agentId}/mcp-connections/${mcpId}/sharing`);
  }

  async updateAgentMCPSharing(
    agentId: string,
    mcpId: string,
    payload: UpdateMCPSharingRequest
  ): Promise<MCPSharingView> {
    return httpClient.put<MCPSharingView>(`/agents/${agentId}/mcp-connections/${mcpId}/sharing`, payload);
  }

  async refreshMCPToolCatalog(mcpId: string): Promise<MCPToolCatalog> {
    return httpClient.post<MCPToolCatalog>(`/connectors/mcp/${mcpId}/tools/refresh`, {});
  }
}

export const connectorApiService = new ConnectorApiService();
