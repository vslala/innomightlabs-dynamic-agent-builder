import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface BuilderSession {
  conversation_id: string;
  provider: string;
  model?: string | null;
  deployment_id?: string | null;
  created_at: string;
}

class BuilderApiService {
  /** Provider and model to build with: the create-agent form's own fields. */
  async getSessionForm(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/builder/session-form");
  }

  async createSession(agentProvider: string, agentModel?: string): Promise<BuilderSession> {
    return httpClient.post<BuilderSession>("/builder/sessions", {
      agent_provider: agentProvider,
      agent_model: agentModel || null,
    });
  }

  async listSessions(): Promise<BuilderSession[]> {
    return httpClient.get<BuilderSession[]>("/builder/sessions");
  }
}

export const builderApiService = new BuilderApiService();
