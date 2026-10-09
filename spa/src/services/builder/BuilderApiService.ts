import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface BuilderSession {
  conversation_id: string;
  provider: string;
  model?: string | null;
  deployment_id?: string | null;
  /** The kit this conversation built or changed. */
  kit_id?: string | null;
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

  /** The person's click on a Connect card: the sign-in address for a popup, or null if already connected. */
  async connect(conversationId: string, provider: string): Promise<{ authorize_url: string | null }> {
    return httpClient.post<{ authorize_url: string | null }>(`/builder/${conversationId}/connect`, { provider });
  }
}

export const builderApiService = new BuilderApiService();
