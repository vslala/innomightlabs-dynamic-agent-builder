import { httpClient } from "../http/client";
import type {
  AutomationGraphResponse,
  AutomationActionCatalogResponse,
  AutomationResponse,
  AutomationSkillResponse,
  AutomationRunDetailResponse,
  AutomationRunResponse,
  CreateAutomationRequest,
  EnableAutomationSkillRequest,
  PaginatedResponse,
  SaveAutomationGraphRequest,
  StartAutomationRunRequest,
  UpdateAutomationRequest,
} from "../../types/automation";

class AutomationApiService {
  async listAutomations(): Promise<AutomationResponse[]> {
    return httpClient.get<AutomationResponse[]>("/automations");
  }

  async createAutomation(data: CreateAutomationRequest): Promise<AutomationGraphResponse> {
    return httpClient.post<AutomationGraphResponse>("/automations", data);
  }

  async getAutomation(automationId: string): Promise<AutomationResponse> {
    return httpClient.get<AutomationResponse>(`/automations/${automationId}`);
  }

  async updateAutomation(
    automationId: string,
    data: UpdateAutomationRequest
  ): Promise<AutomationResponse> {
    return httpClient.patch<AutomationResponse>(`/automations/${automationId}`, data);
  }

  async deleteAutomation(automationId: string): Promise<void> {
    await httpClient.delete(`/automations/${automationId}`);
  }

  async getGraph(automationId: string): Promise<AutomationGraphResponse> {
    return httpClient.get<AutomationGraphResponse>(`/automations/${automationId}/graph`);
  }

  async getActionCatalog(automationId: string): Promise<AutomationActionCatalogResponse> {
    return httpClient.get<AutomationActionCatalogResponse>(`/automations/${automationId}/action-catalog`);
  }

  async listSkills(automationId: string): Promise<AutomationSkillResponse[]> {
    return httpClient.get<AutomationSkillResponse[]>(`/automations/${automationId}/skills`);
  }

  async enableSkill(
    automationId: string,
    skillId: string,
    data: EnableAutomationSkillRequest
  ): Promise<AutomationSkillResponse> {
    return httpClient.post<AutomationSkillResponse>(
      `/automations/${automationId}/skills?skill_id=${encodeURIComponent(skillId)}`,
      data
    );
  }

  async saveGraph(
    automationId: string,
    data: SaveAutomationGraphRequest
  ): Promise<AutomationGraphResponse> {
    return httpClient.put<AutomationGraphResponse>(`/automations/${automationId}/graph`, data);
  }

  async testRun(
    automationId: string,
    data: StartAutomationRunRequest
  ): Promise<AutomationRunResponse> {
    return httpClient.post<AutomationRunResponse>(`/automations/${automationId}/test-run`, data);
  }

  async listRuns(
    automationId: string,
    limit: number = 20,
    cursor?: string | null
  ): Promise<PaginatedResponse<AutomationRunResponse>> {
    const params = new URLSearchParams();
    params.append("limit", limit.toString());
    if (cursor) {
      params.append("cursor", cursor);
    }
    return httpClient.get<PaginatedResponse<AutomationRunResponse>>(
      `/automations/${automationId}/runs?${params.toString()}`
    );
  }

  async getRun(
    automationId: string,
    runId: string
  ): Promise<AutomationRunDetailResponse> {
    return httpClient.get<AutomationRunDetailResponse>(
      `/automations/${automationId}/runs/${runId}`
    );
  }
}

export const automationApiService = new AutomationApiService();
