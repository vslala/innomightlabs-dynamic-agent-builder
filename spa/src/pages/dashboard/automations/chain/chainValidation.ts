/**
 * Continuous client-side checks that drive per-card badges.
 *
 * This mirrors only the cheap rules. The backend stays authoritative: it
 * validates strictly when the automation is activated or test-run, and its
 * message is what the issues panel shows. Nothing here blocks editing or saving,
 * because a draft is allowed to be incomplete.
 */

import type {
  AutomationActionCatalogItem,
  AutomationGraphResponse,
  AutomationNode,
} from "../../../../types/automation";
import type { Chain } from "./chainModel";
import { findCatalogItem, skillActionOf } from "./actionSummary";

export type ChainIssueSeverity = "error" | "warning";

export interface ChainIssue {
  nodeId: string | null;
  severity: ChainIssueSeverity;
  message: string;
}

export function validateChain(
  graph: AutomationGraphResponse,
  chain: Chain,
  catalog: AutomationActionCatalogItem[]
): ChainIssue[] {
  const issues: ChainIssue[] = [];

  chain.unsupported.forEach((nodeId) => {
    issues.push({
      nodeId,
      severity: "error",
      message: "This step uses a connection the linear editor cannot show.",
    });
  });

  if (!chain.items.some((item) => item.kind === "trigger" && item.triggers.length > 0)) {
    issues.push({
      nodeId: null,
      severity: "error",
      message: "Add a trigger so the automation knows when to run.",
    });
  } else if (
    !chain.items.some(
      (item) => item.kind === "trigger" && item.triggers.some((trigger) => trigger.enabled)
    )
  ) {
    issues.push({
      nodeId: null,
      severity: "warning",
      message: "Every trigger is disabled, so this automation will not start on its own.",
    });
  }

  graph.nodes.forEach((node) => {
    if (node.type === "action") issues.push(...actionIssues(node, catalog));
    if (node.type === "condition") issues.push(...conditionIssues(node));
  });

  return issues;
}

function actionIssues(
  node: AutomationNode,
  catalog: AutomationActionCatalogItem[]
): ChainIssue[] {
  const config = skillActionOf(node);
  if (!config) {
    return [{ nodeId: node.node_id, severity: "error", message: "Choose what this step does." }];
  }

  const item = findCatalogItem(node, catalog);
  if (!item) {
    return [
      {
        nodeId: node.node_id,
        severity: "error",
        message: "This action is no longer available.",
      },
    ];
  }
  if (!item.available) {
    return [
      {
        nodeId: node.node_id,
        severity: "error",
        message: item.disabled_reason ?? "This action needs setup before it can run.",
      },
    ];
  }

  const required = requiredArguments(item);
  const missing = required.filter((name) => isBlank(config.arguments?.[name]));
  return missing.map((name) => ({
    nodeId: node.node_id,
    severity: "error" as ChainIssueSeverity,
    message: `${labelForArgument(item, name)} is required.`,
  }));
}

function conditionIssues(node: AutomationNode): ChainIssue[] {
  const expression = node.config.expression;
  if (typeof expression !== "string" || !expression.trim()) {
    return [
      { nodeId: node.node_id, severity: "error", message: "Describe what this condition checks." },
    ];
  }
  return [];
}

export function requiredArguments(item: AutomationActionCatalogItem): string[] {
  const required = (item.input_schema as { required?: unknown }).required;
  return Array.isArray(required) ? required.filter((name): name is string => typeof name === "string") : [];
}

function labelForArgument(item: AutomationActionCatalogItem, name: string): string {
  const field = item.action_form?.form_inputs.find((input) => input.name === name);
  return field?.label ?? name;
}

function isBlank(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
}

export function issuesByNode(issues: ChainIssue[]): Map<string, ChainIssue[]> {
  const byNode = new Map<string, ChainIssue[]>();
  issues.forEach((issue) => {
    if (!issue.nodeId) return;
    const list = byNode.get(issue.nodeId);
    if (list) list.push(issue);
    else byNode.set(issue.nodeId, [issue]);
  });
  return byNode;
}

export function errorCount(issues: ChainIssue[]): number {
  return issues.filter((issue) => issue.severity === "error").length;
}
