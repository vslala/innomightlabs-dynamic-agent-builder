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
  UpdateAgentMCPConnectionRequest,
  UpdateMCPConnectionRequest,
} from "../../types/connectors";

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
}

export const connectorApiService = new ConnectorApiService();
