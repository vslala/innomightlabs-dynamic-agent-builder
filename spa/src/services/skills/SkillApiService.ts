import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";
import type {
  InstalledSkill,
  SkillCatalogItem,
  SkillInstallRequest,
  SkillOAuthStartRequest,
  SkillOAuthStartResponse,
  SkillUpdateRequest,
} from "../../types/skills";

class SkillApiService {
  async listSkills(): Promise<SkillCatalogItem[]> {
    return httpClient.get<SkillCatalogItem[]>("/skills");
  }

  async getSkillInstallSchema(skillId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(`/skills/${skillId}/install-schema`);
  }

  async listInstalledSkills(agentId: string): Promise<InstalledSkill[]> {
    return httpClient.get<InstalledSkill[]>(`/agents/${agentId}/skills`);
  }

  async installSkill(agentId: string, skillId: string, payload: SkillInstallRequest): Promise<InstalledSkill> {
    return httpClient.post<InstalledSkill>(`/agents/${agentId}/skills?skill_id=${encodeURIComponent(skillId)}`, payload);
  }

  async updateInstalledSkill(agentId: string, skillId: string, payload: SkillUpdateRequest): Promise<InstalledSkill> {
    return httpClient.patch<InstalledSkill>(`/agents/${agentId}/skills/${encodeURIComponent(skillId)}`, payload);
  }

  async uninstallSkill(agentId: string, skillId: string, options?: { disconnectOAuth?: boolean }): Promise<void> {
    const params = options?.disconnectOAuth ? "?disconnect_oauth=true" : "";
    await httpClient.delete(`/agents/${agentId}/skills/${encodeURIComponent(skillId)}${params}`);
  }

  async startSkillOAuth(path: string, payload: SkillOAuthStartRequest): Promise<SkillOAuthStartResponse> {
    return httpClient.post<SkillOAuthStartResponse>(path, payload);
  }
}

export const skillApiService = new SkillApiService();
