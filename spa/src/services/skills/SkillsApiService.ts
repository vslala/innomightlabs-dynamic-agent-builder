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

  async getManifestSchema(): Promise<import("../../types/form").FormSchema> {
    return httpClient.get<import("../../types/form").FormSchema>("/skills/forms/manifest");
  }

  async createFromManifest(data: {
    manifest_json: string;
    skill_md?: string;
    secrets?: Array<{ name: string; value: string }>;
  }): Promise<SkillDefinitionResponse> {
    return httpClient.post<SkillDefinitionResponse>("/skills/manifest", data);
  }

  async getEditForm(skill_id: string, version: string): Promise<{ form_schema: import("../../types/form").FormSchema; initial_values: any }> {
    return httpClient.get(`/skills/${skill_id}/${version}/edit-form`);
  }

  async updateSkill(skill_id: string, version: string, data: {
    manifest_json: string;
    skill_md?: string;
    secrets?: Array<{ name: string; value: string }>;
  }): Promise<SkillDefinitionResponse> {
    return httpClient.put<SkillDefinitionResponse>(`/skills/${skill_id}/${version}`, data);
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
