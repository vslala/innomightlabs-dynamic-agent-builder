/**
 * Skills API service.
 *
 * Handles communication with the skills registry and user configuration endpoints.
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

export interface SkillRegistryEntry {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  has_schema: boolean;
}

export interface EnabledSkillResponse {
  skill_id: string;
  config_keys: string[];
  created_at: string;
  updated_at: string;
}

class SkillsApiService {
  async listRegistry(): Promise<SkillRegistryEntry[]> {
    return httpClient.get<SkillRegistryEntry[]>("/skills/registry");
  }

  async getSchema(skillId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(`/skills/${skillId}/schema`);
  }

  async enableSkill(skillId: string, configValues: Record<string, unknown>): Promise<void> {
    await httpClient.post("/skills/enable", {
      skill_id: skillId,
      config_values: configValues,
    });
  }

  async listEnabled(): Promise<EnabledSkillResponse[]> {
    return httpClient.get<EnabledSkillResponse[]>("/skills/enabled");
  }

  async disableSkill(skillId: string): Promise<void> {
    await httpClient.delete(`/skills/${skillId}`);
  }
}

export const skillsApiService = new SkillsApiService();
