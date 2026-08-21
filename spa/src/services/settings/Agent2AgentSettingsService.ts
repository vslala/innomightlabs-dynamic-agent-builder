import { httpClient } from "../http/client";
import type { FormSchema, KeyValueFormValue } from "../../types/form";

export interface Agent2AgentAllowedOrigin {
  origin: string;
  label?: string | null;
}

export interface Agent2AgentSettings {
  allowed_origins: Agent2AgentAllowedOrigin[];
  allowed_origins_map: KeyValueFormValue;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface Agent2AgentSettingsRequest {
  allowed_origins: KeyValueFormValue;
}

class Agent2AgentSettingsService {
  async getSettings(): Promise<Agent2AgentSettings> {
    return httpClient.get<Agent2AgentSettings>("/settings/agent2agent");
  }

  async getSettingsSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/settings/agent2agent/schema");
  }

  async saveSettings(data: Agent2AgentSettingsRequest): Promise<Agent2AgentSettings> {
    return httpClient.put<Agent2AgentSettings>("/settings/agent2agent", data);
  }
}

export const agent2AgentSettingsService = new Agent2AgentSettingsService();
