/**
 * Smart value discovery for the editor.
 *
 * The backend resolver (api/src/automations/smart_values.py) owns evaluation.
 * This module owns discoverability: which references a given step may use, what
 * they are called, and -- when a run is selected -- what they resolved to.
 *
 * Catalog entries come from two places:
 *  - declared fields, from the node type and the skill action it runs
 *  - observed fields, walked out of the selected run's context
 */

import type {
  AutomationActionCatalogItem,
  AutomationGraphResponse,
  AutomationNode,
} from "../../../../types/automation";
import { ancestorNodeIds } from "./chainModel";

export type SmartValueGroupKind = "input" | "trigger" | "step" | "last";

export interface SmartValueField {
  /** Resolver path without braces, e.g. steps.gmail_search.output.response_text */
  path: string;
  label: string;
  description?: string;
  /** Resolved value from the selected run, when there is one. */
  sample?: string;
}

export interface SmartValueGroup {
  id: string;
  kind: SmartValueGroupKind;
  label: string;
  subtitle?: string;
  nodeId?: string;
  fields: SmartValueField[];
}

const INPUT_PLACEHOLDER_PATTERN = /\{\{\s*(?:\$\.)?input\.([a-zA-Z0-9_-]+)/g;

const MAX_SAMPLE_LENGTH = 160;
const MAX_OBSERVED_FIELDS = 32;
// Deep enough to reach the useful shapes skills return, e.g.
// steps.gmail_search.output.result.messages.0.subject
const MAX_OBSERVED_DEPTH = 4;

/** Manual-run input keys referenced anywhere in the graph. */
export function detectInputKeys(graph: AutomationGraphResponse): string[] {
  const keys = new Set<string>();
  graph.nodes.forEach((node) => collectInputKeys(node.config, keys));
  graph.triggers.forEach((trigger) => collectInputKeys(trigger.config, keys));
  return [...keys].sort();
}

function collectInputKeys(value: unknown, keys: Set<string>): void {
  if (typeof value === "string") {
    INPUT_PLACEHOLDER_PATTERN.lastIndex = 0;
    let match = INPUT_PLACEHOLDER_PATTERN.exec(value);
    while (match) {
      keys.add(match[1]);
      match = INPUT_PLACEHOLDER_PATTERN.exec(value);
    }
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => collectInputKeys(item, keys));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value as Record<string, unknown>).forEach((item) => collectInputKeys(item, keys));
  }
}

export function stepReference(node: AutomationNode): string | null {
  return node.alias ? `steps.${node.alias}` : `nodes.${node.node_id}`;
}

export interface SmartValueCatalogInput {
  graph: AutomationGraphResponse;
  /** Step being edited. Only steps that can run before it are offered. */
  forNodeId: string | null;
  catalog: AutomationActionCatalogItem[];
  /** Context of the selected run, used for observed fields and samples. */
  context?: Record<string, unknown> | null;
}

export function buildSmartValueGroups(input: SmartValueCatalogInput): SmartValueGroup[] {
  const { graph, forNodeId, catalog, context } = input;
  const groups: SmartValueGroup[] = [];
  const runInput = readRecord(context, "input");
  const inputKeys = new Set([...detectInputKeys(graph), ...Object.keys(runInput ?? {})]);

  groups.push({
    id: "input",
    kind: "input",
    label: "Manual input",
    subtitle: "Values supplied when the automation runs",
    fields: [
      {
        path: "input",
        label: "Whole input object",
        sample: sampleFor(context, "input"),
      },
      ...[...inputKeys].sort().map((key) => ({
        path: `input.${key}`,
        label: key,
        sample: sampleFor(context, `input.${key}`),
      })),
    ],
  });

  groups.push({
    id: "trigger",
    kind: "trigger",
    label: "Trigger",
    subtitle: "How this run started",
    fields: [
      { path: "trigger.type", label: "Type", sample: sampleFor(context, "trigger.type") },
      { path: "trigger.trigger_id", label: "Trigger id", sample: sampleFor(context, "trigger.trigger_id") },
    ],
  });

  const eligible = eligibleSteps(graph, forNodeId);
  eligible.forEach((node) => {
    const reference = stepReference(node);
    if (!reference) return;
    groups.push({
      id: `step:${node.node_id}`,
      kind: "step",
      label: node.name,
      subtitle: node.alias ?? node.node_id,
      nodeId: node.node_id,
      fields: fieldsForStep(node, reference, catalog, context),
    });
  });

  if (eligible.length > 0) {
    groups.push({
      id: "last",
      kind: "last",
      label: "Previous step",
      subtitle: "Whichever step ran most recently",
      fields: [
        { path: "last.output", label: "Output", sample: sampleFor(context, "last.output") },
        { path: "last.status", label: "Status", sample: sampleFor(context, "last.status") },
      ],
    });
  }

  return groups.filter((group) => group.fields.length > 0);
}

/**
 * Steps that can run before the edited one.
 *
 * Graph ancestry is the right filter: a step further down the chain, or in the
 * sibling branch, can never have produced a value for this one.
 */
export function eligibleSteps(
  graph: AutomationGraphResponse,
  forNodeId: string | null
): AutomationNode[] {
  const editable = graph.nodes.filter((node) => node.type === "action" || node.type === "condition");
  if (!forNodeId) return editable;
  const ancestors = ancestorNodeIds(graph, forNodeId);
  return editable.filter((node) => node.node_id !== forNodeId && ancestors.has(node.node_id));
}

function fieldsForStep(
  node: AutomationNode,
  reference: string,
  catalog: AutomationActionCatalogItem[],
  context?: Record<string, unknown> | null
): SmartValueField[] {
  const declared = declaredFields(node, catalog).map((field) => ({
    ...field,
    path: `${reference}.${field.path}`,
  }));
  const withSamples = declared.map((field) => ({
    ...field,
    sample: sampleFor(context, field.path),
  }));

  const observed = observedFields(reference, context);
  const seen = new Set(withSamples.map((field) => field.path));
  return [...withSamples, ...observed.filter((field) => !seen.has(field.path))];
}

function declaredFields(
  node: AutomationNode,
  catalog: AutomationActionCatalogItem[]
): SmartValueField[] {
  const base: SmartValueField[] = [
    { path: "status", label: "Status", description: "succeeded, failed, or skipped" },
  ];

  if (node.type === "condition") {
    return [{ path: "output.result", label: "Result", description: "true or false" }, ...base];
  }

  const config = node.config as Record<string, unknown>;
  if (config.action_type === "invoke_agent") {
    return [
      { path: "output.response_text", label: "Response text" },
      { path: "output.events", label: "Events" },
      ...base,
    ];
  }

  const skillId = typeof config.skill_id === "string" ? config.skill_id : "";
  const action = typeof config.action === "string" ? config.action : "";
  const item = catalog.find(
    (entry) =>
      entry.action === action &&
      (entry.installed_skill_id === config.installed_skill_id || entry.skill_id === skillId)
  );

  const fields: SmartValueField[] = [
    { path: "output.result", label: "Result", description: item?.description },
  ];
  if (skillId === "agent_invocation" && action === "invoke") {
    fields.push({ path: "output.result.response_text", label: "Agent response" });
  }
  if (skillId === "send_email" && action === "send") {
    fields.push(
      { path: "output.result.sent", label: "Sent" },
      { path: "output.result.recipients", label: "Recipients" }
    );
  }
  return [...fields, ...base];
}

/** Paths actually present in the selected run, so real output shapes are offered. */
function observedFields(
  reference: string,
  context?: Record<string, unknown> | null
): SmartValueField[] {
  const result = resolvePath(context, `${reference}.output`);
  if (result === undefined || result === null || typeof result !== "object") return [];
  const fields: SmartValueField[] = [];
  walkSample(result as Record<string, unknown>, `${reference}.output`, 1, fields);
  return fields.slice(0, MAX_OBSERVED_FIELDS);
}

function walkSample(
  value: Record<string, unknown> | unknown[],
  basePath: string,
  depth: number,
  fields: SmartValueField[]
): void {
  if (depth > MAX_OBSERVED_DEPTH || fields.length >= MAX_OBSERVED_FIELDS) return;
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.slice(0, 3).map((item, index) => [String(index), item])
    : Object.entries(value);

  entries.forEach(([key, item]) => {
    if (fields.length >= MAX_OBSERVED_FIELDS) return;
    if (key === "events") return;
    const path = `${basePath}.${key}`;
    fields.push({ path, label: key, sample: stringifySample(item) });
    if (item && typeof item === "object") {
      walkSample(item as Record<string, unknown>, path, depth + 1, fields);
    }
  });
}

export function resolvePath(context: unknown, path: string): unknown {
  if (!context || typeof context !== "object") return undefined;
  const segments = path.split(".");
  let current: unknown = context;

  if (segments[0] === "last") {
    const execution = (context as Record<string, unknown>).execution;
    const alias =
      execution && typeof execution === "object"
        ? (execution as Record<string, unknown>).last_step_alias
        : undefined;
    if (typeof alias !== "string") return undefined;
    current = resolvePath(context, `steps.${alias}`);
    segments.shift();
  }

  for (const segment of segments) {
    if (current === null || current === undefined) return undefined;
    if (Array.isArray(current)) {
      const index = Number.parseInt(segment, 10);
      if (Number.isNaN(index)) return undefined;
      current = current[index];
      continue;
    }
    if (typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

function readRecord(
  context: Record<string, unknown> | null | undefined,
  key: string
): Record<string, unknown> | null {
  const value = context?.[key];
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function sampleFor(context: Record<string, unknown> | null | undefined, path: string): string | undefined {
  if (!context) return undefined;
  return stringifySample(resolvePath(context, path));
}

export function stringifySample(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text === undefined) return undefined;
  const collapsed = text.replace(/\s+/g, " ").trim();
  if (!collapsed) return undefined;
  return collapsed.length > MAX_SAMPLE_LENGTH
    ? `${collapsed.slice(0, MAX_SAMPLE_LENGTH)}…`
    : collapsed;
}
