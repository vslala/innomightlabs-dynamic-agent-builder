import type { AutomationNodeType } from "./automation";
import type { FormInput, FormSchema, FormValue } from "./form";

export type MarketplaceAutomationStatus = "draft" | "published" | "archived";

export interface MarketplaceAutomationSkillTemplate {
  template_skill_key: string;
  skill_id: string;
  display_name: string | null;
  description: string | null;
  required: boolean;
  enabled_on_import: boolean;
  default_config: Record<string, unknown>;
}

export interface MarketplaceAutomationNodeTemplate {
  node_id: string;
  type: AutomationNodeType;
  name: string;
  description: string | null;
  position: Record<string, unknown>;
  config: Record<string, unknown>;
}

export interface MarketplaceAutomationEdgeTemplate {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  label: string;
  condition: string | null;
}

export interface MarketplaceAutomationImportInput {
  input_key: string;
  label: string;
  description: string | null;
  required: boolean;
  form_input: FormInput;
}

export interface MarketplaceAutomationSummary {
  template_id: string;
  title: string;
  slug: string;
  short_description: string;
  publisher_display_name: string;
  tags: string[];
  node_count: number;
  edge_count: number;
  skill_count: number;
  import_count: number;
  template_version: number;
  created_at: string;
}

export interface MarketplaceAutomationDetail extends MarketplaceAutomationSummary {
  full_description: string;
  automation_title: string;
  automation_description: string | null;
  nodes: MarketplaceAutomationNodeTemplate[];
  edges: MarketplaceAutomationEdgeTemplate[];
  skills: MarketplaceAutomationSkillTemplate[];
  import_inputs: MarketplaceAutomationImportInput[];
  status: MarketplaceAutomationStatus;
  source_automation_id: string | null;
}

export interface MarketplaceAutomationSkillImportForm {
  template_skill_key: string;
  skill_id: string;
  skill_name: string;
  required: boolean;
  form: FormSchema;
}

export interface MarketplaceAutomationImportPlan {
  template_id: string;
  automation: {
    default_title: string;
    description: string | null;
    node_count: number;
    edge_count: number;
  };
  skill_forms: MarketplaceAutomationSkillImportForm[];
  input_form: FormSchema;
}

export interface ImportMarketplaceAutomationRequest {
  session_id?: string | null;
  title?: string;
  description?: string | null;
  skill_configs: Record<string, Record<string, string>>;
  import_inputs: Record<string, string | Record<string, string>>;
}

export interface SaveMarketplaceAutomationImportSessionRequest {
  session_id?: string | null;
  title?: string | null;
  description?: string | null;
  skill_configs?: Record<string, Record<string, string>>;
  import_inputs?: Record<string, string | Record<string, string>>;
}

export interface MarketplaceAutomationImportSession {
  session_id: string;
  template_id: string;
  title: string | null;
  description: string | null;
  skill_configs: Record<string, Record<string, string>>;
  import_inputs: Record<string, string | Record<string, string>>;
  expires_at: string;
}

export interface ImportedMarketplaceAutomationSkill {
  template_skill_key: string;
  installed_skill_id: string;
  skill_id: string;
}

export interface ImportMarketplaceAutomationResponse {
  automation_id: string;
  title: string;
  installed_skills: ImportedMarketplaceAutomationSkill[];
  node_count: number;
  edge_count: number;
}

export interface PublishMarketplaceAutomationRequest {
  automation_id: string;
  title: string;
  short_description: string;
  full_description: string;
  tags: string[];
  included_node_ids: string[];
  included_edge_ids: string[];
  included_skill_ids: string[];
  import_inputs: MarketplaceAutomationImportInput[];
  changelog?: string | null;
  status: "draft" | "published";
}

export interface PublishMarketplaceAutomationResponse {
  template_id: string;
  status: MarketplaceAutomationStatus;
  title: string;
  template_version: number;
}

export type AutomationMarketplaceFormState = Record<string, Record<string, FormValue>>;
