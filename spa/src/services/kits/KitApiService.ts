import { httpClient } from "../http/client";
import type { BlueprintIssue, DeploymentStatus } from "../blueprints/BlueprintApiService";

export type KitStatus = "active" | "removed";
export type KitAction = "apply" | "rollback" | "remove";
export type PlanAction = "create" | "update" | "unchanged" | "remove";

export interface KitSummary {
  kit_id: string;
  title: string;
  description?: string | null;
  status: KitStatus;
  current_version: number;
  versions: number;
  /** How many of each kind it holds, by kind (Agent, KnowledgeBase, WidgetKey, McpConnection). */
  counts: Record<string, number>;
  conversation_id?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface KitResource {
  name: string;
  kind: string;
  id: string;
  title: string;
  /** The dashboard page for it; empty when it has none. */
  dashboard_path: string;
}

export interface KitVersion {
  version: number;
  deployment_id: string;
  action: KitAction;
  status: DeploymentStatus;
  /** What the kit declares now. */
  current: boolean;
  rolled_back_to?: number | null;
  steps: string[];
  removed: string[];
  error?: string | null;
  created_at: string;
}

export interface KitDetail extends KitSummary {
  resources: KitResource[];
  history: KitVersion[];
}

export interface KitPlanStep {
  resource: string;
  kind: string;
  action: PlanAction;
  summary: string;
  changes: string[];
  removals: string[];
  drift: string[];
}

/** What a rollback or a removal would do. Nothing happens until it's applied with its `plan_id`. */
export interface KitPlan {
  ok: boolean;
  plan_id?: string | null;
  steps: KitPlanStep[];
  blockers: BlueprintIssue[];
  removals: string[];
}

class KitApiService {
  async listKits(): Promise<KitSummary[]> {
    return httpClient.get<KitSummary[]>("/kits");
  }

  async getKit(kitId: string): Promise<KitDetail> {
    return httpClient.get<KitDetail>(`/kits/${kitId}`);
  }

  async planRollback(kitId: string, version: number): Promise<KitPlan> {
    return httpClient.post<KitPlan>(`/kits/${kitId}/rollback/plan`, { version });
  }

  /** Goes back to `version`, only if `planId` is still the plan the person saw. */
  async rollback(kitId: string, version: number, planId: string): Promise<void> {
    await httpClient.post(`/kits/${kitId}/rollback`, { version, plan_id: planId });
  }

  async planRemoval(kitId: string): Promise<KitPlan> {
    return httpClient.post<KitPlan>(`/kits/${kitId}/removal/plan`, {});
  }

  /** Deletes everything the kit holds, only if `planId` is still the plan the person saw. */
  async remove(kitId: string, planId: string): Promise<void> {
    await httpClient.post(`/kits/${kitId}/remove`, { plan_id: planId });
  }
}

export const kitApiService = new KitApiService();
