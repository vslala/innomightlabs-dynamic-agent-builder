import { httpClient } from "../http/client";
import type { ConsentAction } from "../../types/consent";

/** What an agent's owner always allows it to do without asking. See docs/LLD-action-consent.md. */
class ConsentApiService {
  /** The agent's actions that ask first (its skills' and MCP connections'), with whether each is always allowed. */
  async listStanding(agentId: string): Promise<ConsentAction[]> {
    return httpClient.get<ConsentAction[]>(`/agents/${agentId}/standing-consents`);
  }

  async alwaysAllow(agentId: string, key: string): Promise<void> {
    await httpClient.put(`/agents/${agentId}/standing-consents/${encodeURIComponent(key)}`, {});
  }

  async askEveryTime(agentId: string, key: string): Promise<void> {
    await httpClient.delete(`/agents/${agentId}/standing-consents/${encodeURIComponent(key)}`);
  }
}

export const consentApiService = new ConsentApiService();
