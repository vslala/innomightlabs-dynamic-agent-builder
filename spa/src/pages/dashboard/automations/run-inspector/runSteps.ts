/**
 * The steps of one run, in the order they ran, each joined to the graph node it ran.
 *
 * A run records results only for the steps it reached, so this is the path the run actually took, not the whole
 * graph. A node deleted since the run still has its result; it is shown under its id.
 */

import type { AutomationNode, AutomationRunNodeResult } from "../../../../types/automation";
import { humanize } from "./toolCalls";

export interface RunStep {
  result: AutomationRunNodeResult;
  node: AutomationNode | null;
}

export type InspectorTab = "activity" | "output" | "input" | "raw";

export function runSteps(results: AutomationRunNodeResult[], nodes: AutomationNode[]): RunStep[] {
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  return [...results]
    .sort((left, right) => Date.parse(left.started_at) - Date.parse(right.started_at))
    .map((result) => ({ result, node: byId.get(result.node_id) ?? null }));
}

export function stepName(step: RunStep): string {
  return step.node?.name || step.result.node_id;
}

/** What kind of step it is, in a person's words: "Ask an agent", "Linkedin · create_post". */
export function stepKind(step: RunStep): string {
  const node = step.node;
  if (!node) return "Removed step";
  if (node.type === "start") return "Trigger";
  if (node.type === "condition") return "Condition";
  if (node.type === "final") return "End";
  const { action_type: actionType, skill_id: skillId, action } = node.config;
  if (actionType === "invoke_agent") return "Ask an agent";
  if (typeof skillId === "string" && typeof action === "string") return `${humanize(skillId)} · ${action}`;
  return "Action";
}

/** Whether the step ran an agent, so it has moves to show (an agent step, or a skill that invokes one). */
export function hasActivity(step: RunStep): boolean {
  return step.result.tool_call_count > 0 || step.node?.config.action_type === "invoke_agent";
}

/** The tab a step opens on: its activity when it has any, else what it produced. */
export function defaultTab(step: RunStep): InspectorTab {
  return hasActivity(step) ? "activity" : "output";
}

export function isInspectorTab(value: string | null): value is InspectorTab {
  return value === "activity" || value === "output" || value === "input" || value === "raw";
}

/** The step worth opening first: where the run failed, else the first one that ran an agent, else the last. */
export function firstStepToInspect(steps: RunStep[]): RunStep | null {
  return (
    steps.find((step) => step.result.status === "failed") ??
    steps.find(hasActivity) ??
    steps[steps.length - 1] ??
    null
  );
}
