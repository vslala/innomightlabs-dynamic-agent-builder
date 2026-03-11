import type { FormSchema } from "./form";

export interface SkillCatalogItem {
  skill_id: string;
  namespace: string;
  name: string;
  description: string;
  action_names: string[];
  has_form: boolean;
}

export interface InstalledSkill {
  skill_id: string;
  namespace: string;
  name: string;
  description: string;
  enabled: boolean;
  installed_at: string;
  updated_at: string | null;
  config: Record<string, string>;
  secret_fields: string[];
}

export interface SkillInstallRequest {
  config: Record<string, string>;
}

export interface SkillUpdateRequest {
  enabled?: boolean;
  config?: Record<string, string>;
}

export type SkillInstallSchema = FormSchema;
