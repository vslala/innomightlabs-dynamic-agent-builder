import { httpClient } from "../http/client";

export type SkillStatus = "active" | "inactive";

export interface SkillDefinitionResponse {
  skill_id: string;
  version: string;
  name: string;
  description: string;
  status: SkillStatus;
  created_at: string;
  updated_at?: string | null;
}

class SkillsApiService {
  async listSkills(): Promise<SkillDefinitionResponse[]> {
    return httpClient.get<SkillDefinitionResponse[]>("/skills");
  }

  async getUploadSchema(): Promise<import("../../types/form").FormSchema> {
    return httpClient.get<import("../../types/form").FormSchema>("/skills/forms/upload");
  }

  async uploadSkillZip(file: File): Promise<SkillDefinitionResponse> {
    const form = new FormData();
    form.append("file", file);
    return httpClient.postForm<SkillDefinitionResponse>("/skills/upload", form);
  }

  async activateSkill(skillId: string, version: string): Promise<SkillDefinitionResponse> {
    return httpClient.post<SkillDefinitionResponse>(`/skills/${skillId}/${version}/activate`, {});
  }

  async deactivateSkill(skillId: string, version: string): Promise<SkillDefinitionResponse> {
    return httpClient.post<SkillDefinitionResponse>(`/skills/${skillId}/${version}/deactivate`, {});
  }
}

export const skillsApiService = new SkillsApiService();
