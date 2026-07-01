import { httpClient } from "../http/client";
import type {
  ImportMarketplaceAgentRequest,
  ImportMarketplaceAgentResponse,
  MarketplaceAgentDetail,
  MarketplaceAgentSummary,
  MarketplaceImportPlan,
  PublishMarketplaceAgentRequest,
  PublishMarketplaceAgentResponse,
} from "../../types/agentMarketplace";

class AgentMarketplaceApiService {
  async listAgents(query?: string): Promise<MarketplaceAgentSummary[]> {
    const params = query?.trim() ? `?query=${encodeURIComponent(query.trim())}` : "";
    return httpClient.get<MarketplaceAgentSummary[]>(`/agent-marketplace/agents${params}`);
  }

  async getAgent(templateId: string): Promise<MarketplaceAgentDetail> {
    return httpClient.get<MarketplaceAgentDetail>(`/agent-marketplace/agents/${encodeURIComponent(templateId)}`);
  }

  async getImportPlan(templateId: string): Promise<MarketplaceImportPlan> {
    return httpClient.get<MarketplaceImportPlan>(`/agent-marketplace/agents/${encodeURIComponent(templateId)}/import-plan`);
  }

  async importAgent(templateId: string, payload: ImportMarketplaceAgentRequest): Promise<ImportMarketplaceAgentResponse> {
    return httpClient.post<ImportMarketplaceAgentResponse>(
      `/agent-marketplace/agents/${encodeURIComponent(templateId)}/import`,
      payload
    );
  }

  async publishAgent(payload: PublishMarketplaceAgentRequest): Promise<PublishMarketplaceAgentResponse> {
    return httpClient.post<PublishMarketplaceAgentResponse>("/agent-marketplace/agents/publish", payload);
  }
}

export const agentMarketplaceApiService = new AgentMarketplaceApiService();
