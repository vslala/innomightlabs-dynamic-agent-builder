import { httpClient } from "../http/client";

export interface DefaultAgentPreference {
  agent_id: string | null;
  updated_at?: string | null;
}

class DefaultAgentService {
  async getDefaultAgent(): Promise<DefaultAgentPreference> {
    return httpClient.get<DefaultAgentPreference>("/settings/default-agent");
  }

  async setDefaultAgent(agentId: string): Promise<DefaultAgentPreference> {
    return httpClient.put<DefaultAgentPreference>("/settings/default-agent", { agent_id: agentId });
  }

  async clearDefaultAgent(): Promise<void> {
    await httpClient.delete<void>("/settings/default-agent");
  }
}

export const defaultAgentService = new DefaultAgentService();
