import type { FormSchema, FormValue } from "./form";

export interface MarketplaceAgentSkillTemplate {
  template_skill_key: string;
  skill_id: string;
  display_name: string | null;
  description: string | null;
  required: boolean;
  enabled_on_import: boolean;
  default_config: Record<string, unknown>;
}

export interface MarketplaceAgentSummary {
  template_id: string;
  title: string;
  slug: string;
  short_description: string;
  publisher_display_name: string;
  tags: string[];
  skill_count: number;
  import_count: number;
  template_version: number;
  created_at: string;
}

export interface MarketplaceAgentDetail extends MarketplaceAgentSummary {
  full_description: string;
  agent_name: string;
  agent_architecture: string;
  agent_provider: string;
  agent_model: string | null;
  allow_model_override: boolean;
  agent_persona: string;
  agent_description: string | null;
  skills: MarketplaceAgentSkillTemplate[];
  status: "draft" | "published" | "archived";
  source_agent_id: string | null;
}

export interface MarketplaceSkillImportForm {
  template_skill_key: string;
  skill_id: string;
  skill_name: string;
  required: boolean;
  form: FormSchema;
}

export interface MarketplaceImportPlan {
  template_id: string;
  agent: {
    default_name: string;
    default_provider: string;
    default_model: string | null;
    allow_model_override: boolean;
    description: string | null;
    persona_preview: string;
  };
  skill_forms: MarketplaceSkillImportForm[];
}

export interface ImportMarketplaceAgentRequest {
  agent_name?: string;
  agent_provider?: string;
  agent_model?: string;
  skill_configs: Record<string, Record<string, string>>;
}

export interface ImportMarketplaceAgentResponse {
  agent_id: string;
  agent_name: string;
  installed_skills: Array<{
    template_skill_key: string;
    installed_skill_id: string;
    skill_id: string;
  }>;
}

export interface PublishMarketplaceAgentRequest {
  agent_id: string;
  title: string;
  short_description: string;
  full_description: string;
  tags: string[];
  included_skill_ids: string[];
  status: "draft" | "published";
  changelog?: string;
}

export interface PublishMarketplaceAgentResponse {
  template_id: string;
  status: "draft" | "published" | "archived";
  title: string;
  template_version: number;
}

export type SkillFormState = Record<string, Record<string, FormValue>>;
