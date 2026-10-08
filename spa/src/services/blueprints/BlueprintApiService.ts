import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";

/** One problem with a blueprint, from YAML errors to plan blockers. */
export interface BlueprintIssue {
  path: string;
  message: string;
  hint?: string | null;
  line?: number | null;
}

export interface BlueprintValidation {
  valid: boolean;
  issues: BlueprintIssue[];
  params_form?: FormSchema | null;
}

export interface BlueprintPlanStep {
  resource: string;
  kind: string;
  action: string;
  summary: string;
}

export interface BlueprintPlan {
  ok: boolean;
  steps: BlueprintPlanStep[];
  blockers: BlueprintIssue[];
  issues: BlueprintIssue[];
}

export type DeploymentStatus = "applying" | "applied" | "failed" | "failed_partial";

export interface DeployedResource {
  kind: string;
  id: string;
  attributes: Record<string, string>;
}

export interface BlueprintDeployment {
  deployment_id: string;
  blueprint_name: string;
  blueprint_title: string;
  status: DeploymentStatus;
  resources: Record<string, DeployedResource>;
  outputs: Record<string, { value: string; description?: string | null }>;
  error?: string | null;
  created_at: string;
}

export interface BlueprintDeploymentSummary {
  deployment_id: string;
  blueprint_name: string;
  blueprint_title: string;
  status: DeploymentStatus;
  created_at: string;
}

export type BlueprintParams = Record<string, string>;

class BlueprintApiService {
  async getExample(name: string): Promise<string> {
    const response = await httpClient.get<{ name: string; yaml: string }>(`/blueprints/examples/${encodeURIComponent(name)}`);
    return response.yaml;
  }

  async validate(yaml: string): Promise<BlueprintValidation> {
    return httpClient.post<BlueprintValidation>("/blueprints/validate", { yaml });
  }

  async plan(yaml: string, params: BlueprintParams): Promise<BlueprintPlan> {
    return httpClient.post<BlueprintPlan>("/blueprints/plan", { yaml, params });
  }

  async apply(yaml: string, params: BlueprintParams): Promise<BlueprintDeployment> {
    return httpClient.post<BlueprintDeployment>("/blueprints/deployments", { yaml, params });
  }

  async listDeployments(): Promise<BlueprintDeploymentSummary[]> {
    return httpClient.get<BlueprintDeploymentSummary[]>("/blueprints/deployments");
  }
}

export const blueprintApiService = new BlueprintApiService();
