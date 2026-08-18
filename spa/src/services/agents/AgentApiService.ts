/**
 * Agent API Service - calls backend REST API for agent CRUD operations.
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

// Backend Agent response type
export interface AgentResponse {
  agent_id: string;
  agent_name: string;
  agent_architecture: string;
  agent_provider: string;
  agent_model: string | null;
  agent_persona: string;
  agent_description?: string | null;
  capabilities?: string[];
  is_agent2agent_enabled?: boolean;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface Agent2AgentSharingResponse {
  agent_id: string;
  enabled: boolean;
  agent_card_url: string;
  service_url: string;
  has_active_api_key: boolean;
}

export type Agent2AgentTaskState =
  | "TASK_STATE_SUBMITTED"
  | "TASK_STATE_WORKING"
  | "TASK_STATE_INPUT_REQUIRED"
  | "TASK_STATE_COMPLETED"
  | "TASK_STATE_FAILED"
  | "TASK_STATE_CANCELED"
  | "TASK_STATE_REJECTED";

export interface Agent2AgentTextPart {
  kind?: "text";
  text: string;
}

export interface Agent2AgentMessage {
  messageId: string;
  role: "ROLE_USER" | "ROLE_AGENT";
  parts: Agent2AgentTextPart[];
  taskId?: string | null;
  contextId?: string | null;
}

export interface Agent2AgentTaskStatus {
  state: Agent2AgentTaskState;
  message?: Agent2AgentMessage | null;
}

export interface Agent2AgentTask {
  id: string;
  contextId: string;
  agentId: string;
  ownerEmail: string;
  clientKeyId: string;
  conversationId: string;
  status: Agent2AgentTaskStatus;
  history: Agent2AgentMessage[];
  artifacts: Record<string, unknown>[];
  createdAt: string;
  updatedAt: string;
  ttl?: number | null;
}

export interface Agent2AgentTaskListResponse {
  items: Agent2AgentTask[];
}

export interface Agent2AgentTaskResponse {
  task: Agent2AgentTask;
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

  async getAgent2AgentSharing(agentId: string): Promise<Agent2AgentSharingResponse> {
    return httpClient.get<Agent2AgentSharingResponse>(`/agents/${agentId}/a2a-sharing`);
  }

  async updateAgent2AgentSharing(
    agentId: string,
    enabled: boolean
  ): Promise<Agent2AgentSharingResponse> {
    return httpClient.put<Agent2AgentSharingResponse>(
      `/agents/${agentId}/a2a-sharing`,
      { enabled }
    );
  }

  async listAgent2AgentTasks(agentId: string): Promise<Agent2AgentTaskListResponse> {
    return httpClient.get<Agent2AgentTaskListResponse>(`/agents/${agentId}/a2a-tasks`);
  }

  async getAgent2AgentTask(
    agentId: string,
    taskId: string
  ): Promise<Agent2AgentTaskResponse> {
    return httpClient.get<Agent2AgentTaskResponse>(
      `/agents/${agentId}/a2a-tasks/${taskId}`
    );
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
