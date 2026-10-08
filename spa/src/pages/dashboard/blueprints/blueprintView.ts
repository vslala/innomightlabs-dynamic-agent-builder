import type { FormValue } from "../../../types/form";
import type { BlueprintIssue, DeploymentStatus } from "../../../services/blueprints/BlueprintApiService";

/** SchemaForm values as blueprint params: only the text values, which is all a params form has. */
export function toParams(values: Record<string, FormValue>): Record<string, string> {
  const params: Record<string, string> = {};
  for (const [name, value] of Object.entries(values)) {
    if (typeof value === "string") {
      params[name] = value;
    }
  }
  return params;
}

/** Where an issue is, as a person would look for it. */
export function issueLocation(issue: BlueprintIssue): string {
  const where = issue.path || "blueprint";
  return issue.line ? `Line ${issue.line} · ${where}` : where;
}

export const DEPLOYMENT_STATUS: Record<DeploymentStatus, { status: "in_progress" | "completed" | "failed" | "warning"; label: string }> = {
  applying: { status: "in_progress", label: "Applying" },
  applied: { status: "completed", label: "Applied" },
  failed: { status: "failed", label: "Failed, rolled back" },
  failed_partial: { status: "warning", label: "Failed, needs cleanup" },
};

/** Dashboard links for the resources a deployment created. */
export function resourceLink(kind: string, id: string): string | null {
  if (kind === "Agent") return `/dashboard/agents/${id}`;
  if (kind === "KnowledgeBase") return `/dashboard/knowledge-bases/${id}`;
  return null;
}
