/**
 * Agent API Service - calls backend REST API for agent CRUD operations.
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

// Backend Agent response type
export interface AgentResponse {
  agent_id: string;
  agent_name: string;
  agent_provider: string;
  agent_persona: string;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

class AgentApiService {
  /**
   * Get the form schema for creating an agent
   */
  async getCreateSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/agents/supported-models");
  }

  /**
   * Get the form schema for updating an agent
   */
  async getUpdateSchema(agentId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(`/agents/update-schema/${agentId}`);
  }

  /**
   * List all agents for the current user
   */
  async listAgents(): Promise<AgentResponse[]> {
    return httpClient.get<AgentResponse[]>("/agents");
  }

  /**
   * Get a single agent by ID
   */
  async getAgent(agentId: string): Promise<AgentResponse> {
    return httpClient.get<AgentResponse>(`/agents/${agentId}`);
  }

  /**
   * Create a new agent
   */
  async createAgent(data: Record<string, string>): Promise<AgentResponse> {
    return httpClient.post<AgentResponse>("/agents", data);
  }

  /**
   * Update an existing agent
   */
  async updateAgent(
    agentId: string,
    data: Record<string, string>
  ): Promise<AgentResponse> {
    return httpClient.put<AgentResponse>(`/agents/${agentId}`, data);
  }

  /**
   * Delete an agent
   */
  async deleteAgent(agentId: string): Promise<void> {
    await httpClient.delete(`/agents/${agentId}`);
  }
}

// Singleton instance
export const agentApiService = new AgentApiService();
