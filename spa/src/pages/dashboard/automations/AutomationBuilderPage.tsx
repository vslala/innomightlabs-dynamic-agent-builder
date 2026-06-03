import "@xyflow/react/dist/style.css";
import "./styles.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeProps,
  type OnEdgesChange,
  type OnNodesChange,
} from "@xyflow/react";
import { Bot, Check, Copy, GitBranch, Lightbulb, Play, Plus, Save, Trash2, Workflow, X } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import {
  Button,
  ErrorState,
  Input,
  Label,
  LoadingState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  Textarea,
} from "../../../components/ui";
import { SchemaForm } from "../../../components/forms";
import { agentApiService, type AgentResponse } from "../../../services/agents/AgentApiService";
import { automationApiService } from "../../../services/automations";
import type {
  AutomationActionCatalogItem,
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationNodePosition,
  AutomationNodeType,
  AutomationRunDetailResponse,
  AutomationSkillResponse,
  CreateAutomationEdgeRequest,
  CreateAutomationNodeRequest,
  InvokeAgentActionConfig,
  SkillActionConfig,
} from "../../../types/automation";
import type { FormSchema, FormValue, SelectOption } from "../../../types/form";
import { AutomationJsonEditor, AutomationJsonTreeViewer } from "./components/AutomationJsonEditor";
import { filterRuntimeLogContext } from "./runDisplay";
import { useAutomationDetailContext } from "./types";

type AutomationFlowNode = Node<{
  automationNode: AutomationNode;
  copied?: boolean;
  onCopyNodeId?: (nodeId: string) => void;
}>;
type AutomationFlowEdge = Edge<{ automationEdge?: AutomationEdge }>;
type BuilderPanelMode = "step" | "smart" | "test" | "configure";

const DEFAULT_PROMPT = "Use the workflow context to complete this step.\n\nInput: {{ $.input }}";
const DEFAULT_SKILL_ACTION = "agent_invocation::invoke";
const TERMINAL_RUN_STATUSES = new Set(["succeeded", "failed", "cancelled"]);
const RUN_POLL_INTERVAL_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function createNodeId(type: AutomationNodeType): string {
  return `${type}-${crypto.randomUUID()}`;
}

async function copyToClipboard(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function isInvokeAgentConfig(config: Record<string, unknown>): boolean {
  return config.action_type === "invoke_agent";
}

function getInvokeAgentConfig(config: Record<string, unknown>): InvokeAgentActionConfig {
  if (isInvokeAgentConfig(config)) {
    return {
      action_type: "invoke_agent",
      agent_id: typeof config.agent_id === "string" ? config.agent_id : "",
      prompt_template: typeof config.prompt_template === "string" ? config.prompt_template : "",
      input: typeof config.input === "object" && config.input !== null ? config.input as Record<string, unknown> : {},
    };
  }
  return { action_type: "invoke_agent", agent_id: "", prompt_template: "", input: {} };
}

function isSkillActionConfig(config: Record<string, unknown>): boolean {
  return config.action_type === "skill_action";
}

function getSkillActionConfig(config: Record<string, unknown>): SkillActionConfig {
  if (isSkillActionConfig(config)) {
    return {
      action_type: "skill_action",
      installed_skill_id: typeof config.installed_skill_id === "string" ? config.installed_skill_id : null,
      skill_id: typeof config.skill_id === "string" ? config.skill_id : "",
      action: typeof config.action === "string" ? config.action : "",
      arguments:
        typeof config.arguments === "object" && config.arguments !== null
          ? (config.arguments as Record<string, unknown>)
          : {},
    };
  }
  if (isInvokeAgentConfig(config)) {
    const invokeConfig = getInvokeAgentConfig(config);
    return {
      action_type: "skill_action",
      skill_id: "agent_invocation",
      action: "invoke",
      arguments: {
        agent_id: invokeConfig.agent_id,
        prompt_template: invokeConfig.prompt_template,
      },
    };
  }
  return {
    action_type: "skill_action",
    skill_id: "agent_invocation",
    action: "invoke",
    arguments: { agent_id: "", prompt_template: DEFAULT_PROMPT },
  };
}

function skillActionKey(config: SkillActionConfig): string {
  return `${config.installed_skill_id || config.skill_id || ""}::${config.action}`;
}

function catalogActionKey(item: AutomationActionCatalogItem): string {
  return `${item.installed_skill_id || item.skill_id}::${item.action}`;
}

function formValuesToConfig(values: Record<string, FormValue>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => {
      if (typeof value === "string") return [key, value];
      return [key, value ?? ""];
    })
  );
}

function findCatalogActionForInstalledSkill(
  catalog: AutomationActionCatalogItem[],
  installed: AutomationSkillResponse,
  actionName: string,
): AutomationActionCatalogItem | null {
  return catalog.find(
    (item) =>
      item.installed_skill_id === installed.installed_skill_id &&
      item.skill_id === installed.skill_id &&
      item.action === actionName
  ) ?? null;
}

function buildWorkflowSmartValueExamples(
  steps: AutomationNode[],
  actionCatalog: AutomationActionCatalogItem[],
  currentNodeId: string,
): SmartValueExample[] {
  const examples: SmartValueExample[] = [
    {
      label: "Manual input",
      value: "{{ $.input.input }}",
      description: "The text supplied when the automation is tested or manually run.",
    },
    {
      label: "Manual input object",
      value: "{{ $.input }}",
      description: "Complete input object supplied when the automation starts.",
    },
    {
      label: "Trigger type",
      value: "{{ $.trigger.type }}",
      description: "The trigger source, such as manual.",
    },
  ];

  steps
    .filter((step) => step.node_id !== currentNodeId)
    .forEach((step) => {
      examples.push(...buildStepSmartValueExamples(step, actionCatalog));
    });

  return examples;
}

function buildStepSmartValueExamples(
  step: AutomationNode,
  actionCatalog: AutomationActionCatalogItem[],
): SmartValueExample[] {
  const basePath = `$.nodes.${step.node_id}`;
  const examples: SmartValueExample[] = [
    {
      label: `${step.name} status`,
      value: `{{ ${basePath}.status }}`,
      description: "Execution status for this step.",
    },
    {
      label: `${step.name} output`,
      value: `{{ ${basePath}.output }}`,
      description: "Complete output object from this step.",
    },
  ];

  if (step.type === "condition") {
    examples.push({
      label: `${step.name} result`,
      value: `{{ ${basePath}.output.result }}`,
      description: "Boolean result from this condition step.",
    });
    return examples;
  }

  if (step.type !== "action") {
    return examples;
  }

  if (isInvokeAgentConfig(step.config)) {
    examples.push({
      label: `${step.name} response`,
      value: `{{ ${basePath}.output.response_text }}`,
      description: "Agent response text from this invoke-agent step.",
    });
    return examples;
  }

  const skillConfig = getSkillActionConfig(step.config);
  const catalogItem = actionCatalog.find(
    (item) => catalogActionKey(item) === skillActionKey(skillConfig)
  );
  const actionLabel = catalogItem?.label ?? `${skillConfig.skill_id || "Skill"}: ${skillConfig.action}`;

  examples.push(
    {
      label: `${step.name} result`,
      value: `{{ ${basePath}.output.result }}`,
      description: `Complete result returned by ${actionLabel}.`,
    },
    {
      label: `${step.name} action arguments`,
      value: `{{ ${basePath}.output.arguments }}`,
      description: "Rendered arguments used by this skill action.",
    },
  );

  const knownResultFields = smartValueResultFieldsForSkillAction(skillConfig, catalogItem);
  knownResultFields.forEach((field) => {
    examples.push({
      label: `${step.name} ${field.label}`,
      value: `{{ ${basePath}.output.result.${field.path} }}`,
      description: field.description,
    });
  });

  return examples;
}

function smartValueResultFieldsForSkillAction(
  config: SkillActionConfig,
  catalogItem?: AutomationActionCatalogItem | null,
): Array<{ label: string; path: string; description: string }> {
  const skillId = catalogItem?.skill_id ?? config.skill_id;
  if (skillId === "agent_invocation" && config.action === "invoke") {
    return [
      {
        label: "response",
        path: "response_text",
        description: "Response text returned by the invoked agent.",
      },
    ];
  }
  if (skillId === "send_email" && config.action === "send") {
    return [
      {
        label: "sent",
        path: "sent",
        description: "Whether at least one configured recipient was sent successfully.",
      },
      {
        label: "recipients",
        path: "recipients",
        description: "Per-recipient delivery status for the email.",
      },
    ];
  }
  return [];
}

function hydrateActionForm(schema: FormSchema, agents: AgentResponse[]): FormSchema {
  return {
    ...schema,
    form_inputs: schema.form_inputs.map((field) => {
      if (field.options_source?.type !== "agents" && field.attr?.source !== "agents") return field;
      const options: SelectOption[] = agents.map((agent) => ({
        value: agent.agent_id,
        label: agent.agent_name,
      }));
      return { ...field, options };
    }),
  };
}

function formValuesToArguments(
  values: Record<string, FormValue>,
  inputSchema: Record<string, unknown>
): Record<string, unknown> {
  const properties =
    typeof inputSchema.properties === "object" && inputSchema.properties !== null
      ? inputSchema.properties as Record<string, { type?: string }>
      : {};
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value instanceof FileList || Array.isArray(value)) continue;
    if (typeof value === "object") {
      result[key] = value;
      continue;
    }
    const type = properties[key]?.type;
    if (type === "boolean") {
      result[key] = value === "true";
    } else if (type === "integer") {
      const parsed = Number.parseInt(String(value), 10);
      if (Number.isFinite(parsed)) result[key] = parsed;
    } else if (type === "number") {
      const parsed = Number.parseFloat(String(value));
      if (Number.isFinite(parsed)) result[key] = parsed;
    } else if (value !== "") {
      result[key] = value;
    }
  }
  return result;
}

function argumentsToFormValues(argumentsValue: Record<string, unknown>): Record<string, FormValue> {
  return Object.fromEntries(
    Object.entries(argumentsValue).map(([key, value]) => {
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        return [key, value as Record<string, string>];
      }
      return [key, value == null ? "" : String(value)];
    })
  );
}

function toFlowNodes(
  nodes: AutomationNode[],
  options: {
    copiedNodeId?: string | null;
    onCopyNodeId?: (nodeId: string) => void;
  } = {}
): AutomationFlowNode[] {
  return nodes.map((node, index) => ({
    id: node.node_id,
    type: "automation",
    position: {
      x: Number(node.position?.x ?? 120 + index * 260),
      y: Number(node.position?.y ?? 120),
    },
    data: {
      automationNode: node,
      copied: options.copiedNodeId === node.node_id,
      onCopyNodeId: options.onCopyNodeId,
    },
  }));
}

function isFinitePosition(position: AutomationNodePosition | undefined): position is Required<Pick<AutomationNodePosition, "x" | "y">> {
  return Number.isFinite(Number(position?.x)) && Number.isFinite(Number(position?.y));
}

function getNodePosition(node: AutomationNode | undefined, fallback: { x: number; y: number }): { x: number; y: number } {
  if (isFinitePosition(node?.position)) {
    return { x: Number(node.position.x), y: Number(node.position.y) };
  }
  return fallback;
}

function normalizeGraph(graph: AutomationGraphResponse): { graph: AutomationGraphResponse; changed: boolean } {
  const now = new Date().toISOString();
  let changed = false;
  let nodes = [...graph.nodes];
  let edges = [...graph.edges];
  let triggers = [...graph.triggers];

  let start = nodes.find((node) => node.type === "start");
  if (!start) {
    changed = true;
    start = {
      node_id: createNodeId("start"),
      automation_id: graph.automation.automation_id,
      type: "start",
      name: "Start",
      description: null,
      position: { x: 80, y: 220 },
      config: {},
      created_at: now,
      updated_at: null,
    };
    nodes = [start, ...nodes];
  }

  let final = nodes.find((node) => node.type === "final");
  if (!final) {
    changed = true;
    final = {
      node_id: createNodeId("final"),
      automation_id: graph.automation.automation_id,
      type: "final",
      name: "Done",
      description: null,
      position: { x: 620, y: 220 },
      config: {},
      created_at: now,
      updated_at: null,
    };
    nodes = [...nodes, final];
  }

  const nonSystemNodes = nodes.filter((node) => node.type !== "start" && node.type !== "final");
  nodes = nodes.map((node, index) => {
    const existingX = Number(node.position?.x);
    const existingY = Number(node.position?.y);
    const hasVisiblePosition =
      Number.isFinite(existingX) &&
      Number.isFinite(existingY) &&
      existingX > -2000 &&
      existingX < 4000 &&
      existingY > -2000 &&
      existingY < 4000;

    if (hasVisiblePosition && node.position?.x === existingX && node.position?.y === existingY) {
      return node;
    }

    changed = true;
    if (node.type === "start") {
      return { ...node, position: { ...(node.position ?? {}), x: 80, y: 220 } };
    }
    if (node.type === "final") {
      return { ...node, position: { ...(node.position ?? {}), x: 380 + nonSystemNodes.length * 280, y: 220 } };
    }
    return {
      ...node,
      position: {
        ...(node.position ?? {}),
        x: 360 + index * 240,
        y: node.type === "condition" ? 300 : 220,
      },
    };
  });

  const hasAnyValidEdge = edges.some((edge) =>
    nodes.some((node) => node.node_id === edge.source_node_id) &&
    nodes.some((node) => node.node_id === edge.target_node_id)
  );
  if (!hasAnyValidEdge && start && final) {
    changed = true;
    edges = [
      {
        edge_id: `${start.node_id}-${final.node_id}`,
        automation_id: graph.automation.automation_id,
        source_node_id: start.node_id,
        target_node_id: final.node_id,
        label: "next",
        condition: null,
        created_at: now,
        updated_at: null,
      },
    ];
  }

  if (!triggers.some((trigger) => trigger.type === "manual") && start) {
    changed = true;
    triggers = [
      ...triggers,
      {
        trigger_id: createNodeId("start"),
        automation_id: graph.automation.automation_id,
        type: "manual",
        name: "Manual",
        enabled: true,
        entry_node_id: start.node_id,
        config: {},
        created_at: now,
        updated_at: null,
      },
    ];
  }

  return { graph: { ...graph, nodes, edges, triggers }, changed };
}

function createGraphWithDraftStep(graph: AutomationGraphResponse): { graph: AutomationGraphResponse; nodeId: string | null } {
  const normalized = normalizeGraph(graph);
  const result = insertDraftStep(normalized.graph);
  return { graph: result.graph, nodeId: result.nodeId };
}

function layoutGraphAfterInsert(graph: AutomationGraphResponse, insertedNodeId?: string | null): AutomationGraphResponse {
  const startNode = graph.nodes.find((node) => node.type === "start");
  const startPosition = getNodePosition(startNode, { x: 80, y: 220 });
  const editableNodes = graph.nodes.filter((node) => node.type !== "start" && node.type !== "final");

  return {
    ...graph,
    nodes: graph.nodes.map((node) => {
      if (node.type === "start") {
        return { ...node, position: getNodePosition(node, { x: 80, y: 220 }) };
      }

      if (node.type === "final") {
        const finalPosition = {
          x: startPosition.x + (editableNodes.length + 1) * 280,
          y: startPosition.y,
        };
        return insertedNodeId ? { ...node, position: finalPosition } : { ...node, position: getNodePosition(node, finalPosition) };
      }

      const index = editableNodes.findIndex((item) => item.node_id === node.node_id);
      const position = {
        x: startPosition.x + (index + 1) * 280,
        y: startPosition.y + (node.type === "condition" ? 80 : 0),
      };

      if (node.node_id === insertedNodeId || !isFinitePosition(node.position)) {
        return { ...node, position };
      }

      return node;
    }),
  };
}

function toFlowEdges(edges: AutomationEdge[], selectedEdgeId?: string | null): AutomationFlowEdge[] {
  return edges.map((edge) => ({
    id: edge.edge_id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    label: edge.label,
    type: "smoothstep",
    animated: edge.label === "true" || edge.label === "false",
    data: { automationEdge: edge },
    selected: selectedEdgeId === edge.edge_id,
    style: {
      stroke: edge.label === "false" ? "#f97316" : edge.label === "true" ? "#22c55e" : "#667eea",
      strokeWidth: selectedEdgeId === edge.edge_id ? 3 : 2,
    },
  }));
}

function graphToSaveRequest(graph: AutomationGraphResponse) {
  const nodes: CreateAutomationNodeRequest[] = graph.nodes.map((node) => ({
    node_id: node.node_id,
    type: node.type,
    name: node.name,
    description: node.description,
    position: node.position,
    config: node.config,
  }));
  const edges: CreateAutomationEdgeRequest[] = graph.edges.map((edge) => ({
    edge_id: edge.edge_id,
    source_node_id: edge.source_node_id,
    target_node_id: edge.target_node_id,
    label: edge.label,
    condition: edge.condition,
  }));
  return { nodes, edges };
}

function actionConfig(): SkillActionConfig {
  return {
    action_type: "skill_action",
    skill_id: "agent_invocation",
    action: "invoke",
    arguments: {
      agent_id: "",
      prompt_template: DEFAULT_PROMPT,
    },
  };
}

function toConfigRecord(config: SkillActionConfig | InvokeAgentActionConfig | ReturnType<typeof conditionConfig>): Record<string, unknown> {
  return { ...config };
}

function conditionConfig() {
  return {
    expression: "$.input",
    true_label: "true",
    false_label: "false",
  };
}

function patchNode(
  graph: AutomationGraphResponse,
  nodeId: string,
  patch: Partial<Pick<AutomationNode, "type" | "name" | "description" | "position" | "config">>
): AutomationGraphResponse {
  return {
    ...graph,
    nodes: graph.nodes.map((node) => (node.node_id === nodeId ? { ...node, ...patch } : node)),
  };
}

function insertNodeAfter(
  graph: AutomationGraphResponse,
  sourceNodeId: string,
  type: "action" | "condition" = "action"
): AutomationGraphResponse {
  const source = graph.nodes.find((node) => node.node_id === sourceNodeId);
  if (!source || source.type === "final") return graph;

  const outgoing = graph.edges.find((edge) => edge.source_node_id === sourceNodeId && edge.label === "next");
  const targetNodeId = outgoing?.target_node_id;
  const newNodeId = createNodeId(type);
  const basePosition = source.position;
  const newNode: AutomationNode = {
    node_id: newNodeId,
    automation_id: graph.automation.automation_id,
    type,
    name: "New Step",
    description: null,
    position: {
      x: Number(basePosition.x ?? 120) + 280,
      y: Number(basePosition.y ?? 120) + (type === "condition" ? 40 : 0),
    },
    config:
      type === "action"
        ? toConfigRecord(actionConfig())
        : toConfigRecord(conditionConfig()),
    created_at: new Date().toISOString(),
    updated_at: null,
  };

  const edges = graph.edges.filter((edge) => edge.edge_id !== outgoing?.edge_id);
  const nextTarget = targetNodeId ?? graph.nodes.find((node) => node.type === "final")?.node_id;
  const newEdges: AutomationEdge[] =
    type === "condition" && nextTarget
      ? [
          {
            edge_id: createNodeId("condition"),
            automation_id: graph.automation.automation_id,
            source_node_id: sourceNodeId,
            target_node_id: newNodeId,
            label: "next",
            condition: null,
            created_at: new Date().toISOString(),
            updated_at: null,
          },
          {
            edge_id: `${newNodeId}-true`,
            automation_id: graph.automation.automation_id,
            source_node_id: newNodeId,
            target_node_id: nextTarget,
            label: "true",
            condition: null,
            created_at: new Date().toISOString(),
            updated_at: null,
          },
          {
            edge_id: `${newNodeId}-false`,
            automation_id: graph.automation.automation_id,
            source_node_id: newNodeId,
            target_node_id: nextTarget,
            label: "false",
            condition: null,
            created_at: new Date().toISOString(),
            updated_at: null,
          },
        ]
      : [
          {
            edge_id: `${sourceNodeId}-${newNodeId}`,
            automation_id: graph.automation.automation_id,
            source_node_id: sourceNodeId,
            target_node_id: newNodeId,
            label: "next",
            condition: null,
            created_at: new Date().toISOString(),
            updated_at: null,
          },
          ...(nextTarget
            ? [{
                edge_id: `${newNodeId}-${nextTarget}`,
                automation_id: graph.automation.automation_id,
                source_node_id: newNodeId,
                target_node_id: nextTarget,
                label: "next",
                condition: null,
                created_at: new Date().toISOString(),
                updated_at: null,
              }]
            : []),
        ];

  return { ...graph, nodes: [...graph.nodes, newNode], edges: [...edges, ...newEdges] };
}

function insertDraftStep(graph: AutomationGraphResponse): { graph: AutomationGraphResponse; nodeId: string | null } {
  const finalNode = graph.nodes.find((node) => node.type === "final");
  const sourceEdge = finalNode
    ? graph.edges.find((edge) => edge.target_node_id === finalNode.node_id && edge.label === "next")
    : null;
  const sourceNode =
    (sourceEdge ? graph.nodes.find((node) => node.node_id === sourceEdge.source_node_id) : null) ??
    graph.nodes.find((node) => node.type === "start") ??
    graph.nodes.find((node) => node.type !== "final");

  if (!sourceNode) {
    return { graph, nodeId: null };
  }

  const next = insertNodeAfter(graph, sourceNode.node_id, "action");
  if (next === graph) {
    return { graph, nodeId: null };
  }
  const insertedCandidates = next.nodes.filter(
    (node) =>
      node.type !== "start" &&
      node.type !== "final" &&
      !graph.nodes.some((existing) => existing.node_id === node.node_id)
  );
  const inserted = insertedCandidates[insertedCandidates.length - 1] ?? null;
  return { graph: next, nodeId: inserted?.node_id ?? null };
}

function updateStepType(
  graph: AutomationGraphResponse,
  nodeId: string,
  type: "action" | "condition"
): AutomationGraphResponse {
  const node = graph.nodes.find((item) => item.node_id === nodeId);
  if (!node || node.type === "start" || node.type === "final" || node.type === type) {
    return graph;
  }

  const nextConfig = type === "action" ? toConfigRecord(actionConfig()) : toConfigRecord(conditionConfig());
  const nextName = node.name === "New Step" || node.name === "Invoke Agent" || node.name === "Condition"
    ? type === "action" ? "Invoke Agent" : "Condition"
    : node.name;

  let edges = graph.edges;
  if (type === "condition") {
    const outgoingNext = graph.edges.find((edge) => edge.source_node_id === nodeId && edge.label === "next");
    if (outgoingNext) {
      edges = [
        ...graph.edges.filter((edge) => edge.edge_id !== outgoingNext.edge_id),
        { ...outgoingNext, edge_id: `${nodeId}-true`, label: "true" },
        { ...outgoingNext, edge_id: `${nodeId}-false`, label: "false" },
      ];
    }
  } else {
    const outgoing = graph.edges.filter((edge) => edge.source_node_id === nodeId);
    const trueEdge = outgoing.find((edge) => edge.label === "true");
    const falseEdge = outgoing.find((edge) => edge.label === "false");
    if (trueEdge || falseEdge) {
      const keep = trueEdge ?? falseEdge;
      edges = [
        ...graph.edges.filter((edge) => edge.source_node_id !== nodeId),
        ...(keep ? [{ ...keep, edge_id: `${nodeId}-${keep.target_node_id}`, label: "next" }] : []),
      ];
    }
  }

  return {
    ...graph,
    edges,
    nodes: graph.nodes.map((item) =>
      item.node_id === nodeId
        ? { ...item, type, name: nextName, config: nextConfig }
        : item
    ),
  };
}

function deleteNode(graph: AutomationGraphResponse, nodeId: string): AutomationGraphResponse {
  const node = graph.nodes.find((item) => item.node_id === nodeId);
  if (!node || node.type === "start" || node.type === "final") return graph;
  return {
    ...graph,
    nodes: graph.nodes.filter((item) => item.node_id !== nodeId),
    edges: graph.edges.filter((edge) => edge.source_node_id !== nodeId && edge.target_node_id !== nodeId),
  };
}

function deleteEdge(graph: AutomationGraphResponse, edgeId: string): AutomationGraphResponse {
  return {
    ...graph,
    edges: graph.edges.filter((edge) => edge.edge_id !== edgeId),
  };
}

function formatJsonText(value: string): { value: string; error: string | null } {
  try {
    return { value: JSON.stringify(JSON.parse(value), null, 2), error: null };
  } catch (err) {
    return { value, error: err instanceof Error ? err.message : "Invalid JSON" };
  }
}

function automationRunBadgeStatus(status: string) {
  if (status === "succeeded") return "success";
  if (status === "running") return "in_progress";
  if (status === "skipped") return "inactive";
  return status as "pending" | "failed" | "cancelled" | "success" | "in_progress" | "inactive";
}

function AutomationNodeCard({ data, selected }: NodeProps<AutomationFlowNode>) {
  const node = data.automationNode;
  const Icon = node.type === "action" ? Bot : node.type === "condition" ? GitBranch : Workflow;
  const smartValue = `{{ $.nodes.${node.node_id}.output.response_text }}`;

  return (
    <div className={`automation-node-card automation-node-card--${node.type} ${selected ? "selected" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="automation-node-card__header">
        <Icon className="h-4 w-4" />
        <span>{node.name}</span>
        <button
          type="button"
          className="automation-node-card__copy nodrag nopan"
          onClick={(event) => {
            event.stopPropagation();
            data.onCopyNodeId?.(node.node_id);
          }}
          title={`Copy node ID. Example: ${smartValue}`}
          aria-label={`Copy node ID for ${node.name}`}
        >
          {data.copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </button>
      </div>
      <div className="automation-node-card__meta">{node.type}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { automation: AutomationNodeCard };

export function AutomationBuilderPage() {
  return (
    <ReactFlowProvider>
      <AutomationBuilderContent />
    </ReactFlowProvider>
  );
}

function AutomationBuilderContent() {
  const { fitView } = useReactFlow<AutomationFlowNode, AutomationFlowEdge>();
  const { automationId } = useParams<{ automationId: string }>();
  const navigate = useNavigate();
  const { automation, reloadAutomation } = useAutomationDetailContext();
  const [graph, setGraph] = useState<AutomationGraphResponse | null>(null);
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [panelMode, setPanelMode] = useState<BuilderPanelMode>("step");
  const [runInput, setRunInput] = useState("{\n  \"input\": \"\"\n}");
  const [runInputError, setRunInputError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [latestRun, setLatestRun] = useState<AutomationRunDetailResponse | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [copiedNodeId, setCopiedNodeId] = useState<string | null>(null);
  const [flowNodes, setFlowNodes] = useState<AutomationFlowNode[]>([]);
  const [flowEdges, setFlowEdges] = useState<AutomationFlowEdge[]>([]);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [actionCatalog, setActionCatalog] = useState<AutomationActionCatalogItem[]>([]);
  const [configuringAction, setConfiguringAction] = useState<AutomationActionCatalogItem | null>(null);
  const [configuringActionNodeId, setConfiguringActionNodeId] = useState<string | null>(null);
  const [configuringActionError, setConfiguringActionError] = useState<string | null>(null);
  const [configuringActionSubmitting, setConfiguringActionSubmitting] = useState(false);
  const [copiedSmartValue, setCopiedSmartValue] = useState<string | null>(null);
  const activeRunPollId = useRef(0);

  const loadGraph = useCallback(async () => {
    if (!automationId) return;
    setLoading(true);
    setError(null);
    try {
      const [graphData, agentsData] = await Promise.all([
        automationApiService.getGraph(automationId),
        agentApiService.listAgents(),
      ]);
      const catalogData = await automationApiService.getActionCatalog(automationId);
      const normalized = normalizeGraph(graphData);
      setGraph(normalized.graph);
      setAgents(agentsData);
      setActionCatalog(catalogData.actions);
      setSelectedNodeId(normalized.graph.nodes.find((node) => node.type === "start")?.node_id ?? null);
      setDirty(normalized.changed);
    } catch (err) {
      console.error("Error loading automation graph:", err);
      setError("Failed to load automation builder. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [automationId]);

  useEffect(() => {
    void loadGraph();
  }, [loadGraph]);

  useEffect(() => () => {
    activeRunPollId.current += 1;
  }, []);

  const handleCopyNodeId = useCallback(async (nodeId: string) => {
    try {
      await copyToClipboard(nodeId);
      setCopiedNodeId(nodeId);
      window.setTimeout(() => setCopiedNodeId((current) => (current === nodeId ? null : current)), 1400);
    } catch (err) {
      console.error("Error copying node ID:", err);
      setMutationError("Failed to copy node ID.");
    }
  }, []);

  useEffect(() => {
    setFlowNodes(graph ? toFlowNodes(graph.nodes, { copiedNodeId, onCopyNodeId: handleCopyNodeId }) : []);
  }, [copiedNodeId, graph, handleCopyNodeId]);

  useEffect(() => {
    setFlowEdges(graph ? toFlowEdges(graph.edges, selectedEdgeId) : []);
  }, [graph, selectedEdgeId]);

  const selectedNode = graph?.nodes.find((node) => node.node_id === selectedNodeId) ?? null;
  const selectedEdge = graph?.edges.find((edge) => edge.edge_id === selectedEdgeId) ?? null;
  const editableSteps = useMemo(
    () => graph?.nodes.filter((node) => node.type !== "start" && node.type !== "final") ?? [],
    [graph]
  );
  const smartValueExamples = useMemo(
    () => buildWorkflowSmartValueExamples(editableSteps, actionCatalog, selectedNodeId ?? ""),
    [actionCatalog, editableSteps, selectedNodeId]
  );

  useEffect(() => {
    if (flowNodes.length === 0) return;
    const timeout = window.setTimeout(() => {
      fitView({ padding: 0.2, duration: 200 });
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [fitView, flowNodes.length]);

  const updateGraph = useCallback((updater: (current: AutomationGraphResponse) => AutomationGraphResponse) => {
    setGraph((current) => {
      if (!current) return current;
      setDirty(true);
      return updater(current);
    });
  }, []);

  const handleNodesChange: OnNodesChange<AutomationFlowNode> = (changes) => {
    setFlowNodes((current) => applyNodeChanges(changes, current));
  };

  const removeSelectedEdge = useCallback(() => {
    if (!selectedEdgeId) {
      return;
    }
    updateGraph((current) => deleteEdge(current, selectedEdgeId));
    setSelectedEdgeId(null);
  }, [selectedEdgeId, updateGraph]);

  const handleEdgesChange: OnEdgesChange<AutomationFlowEdge> = (changes) => {
    setFlowEdges((current) => applyEdgeChanges(changes, current));
    const removedEdgeIds = changes
      .filter((change): change is EdgeChange<AutomationFlowEdge> & { type: "remove" } => change.type === "remove")
      .map((change) => change.id);

    if (removedEdgeIds.length === 0) {
      return;
    }

    updateGraph((current) => ({
      ...current,
      edges: current.edges.filter((edge) => !removedEdgeIds.includes(edge.edge_id)),
    }));
    setSelectedEdgeId((current) => (current && removedEdgeIds.includes(current) ? null : current));
  };

  useEffect(() => {
    if (!selectedEdgeId) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Delete" && event.key !== "Backspace") {
        return;
      }

      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)
      ) {
        return;
      }

      event.preventDefault();
      removeSelectedEdge();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [removeSelectedEdge, selectedEdgeId]);

  const commitNodePosition = (nodeId: string, position: AutomationNodePosition) => {
    if (!Number.isFinite(Number(position.x)) || !Number.isFinite(Number(position.y))) {
      return;
    }
    updateGraph((current) => {
      const node = current.nodes.find((item) => item.node_id === nodeId);
      if (!node) return current;
      const currentX = Number(node.position?.x);
      const currentY = Number(node.position?.y);
      if (currentX === position.x && currentY === position.y) return current;
      return patchNode(current, nodeId, { position });
    });
  };

  const handleConnect = (connection: Connection) => {
    if (!connection.source || !connection.target) return;
    updateGraph((current) => {
      const edge: AutomationEdge = {
        edge_id: `${connection.source}-${connection.target}`,
        automation_id: current.automation.automation_id,
        source_node_id: connection.source,
        target_node_id: connection.target,
        label: "next",
        condition: null,
        created_at: new Date().toISOString(),
        updated_at: null,
      };
      return { ...current, edges: [...current.edges, edge] };
    });
  };

  const addStep = () => {
    updateGraph((current) => {
      const result = createGraphWithDraftStep(current);
      const nextGraph = layoutGraphAfterInsert(result.graph, result.nodeId);
      window.setTimeout(() => {
        setSelectedNodeId(result.nodeId ?? null);
        if (result.nodeId) {
          fitView({ nodes: [{ id: result.nodeId }], padding: 0.65, duration: 220 });
        }
      }, 0);
      return nextGraph;
    });
  };

  const placeNodeOnCanvas = (nodeId: string) => {
    updateGraph((current) => {
      const startNode = current.nodes.find((node) => node.type === "start");
      const startPosition = getNodePosition(startNode, { x: 80, y: 220 });
      const editableNodes = current.nodes.filter((node) => node.type !== "start" && node.type !== "final");
      const index = Math.max(0, editableNodes.findIndex((node) => node.node_id === nodeId));
      return patchNode(current, nodeId, {
        position: {
          x: startPosition.x + (index + 1) * 280,
          y: startPosition.y,
        },
      });
    });
    setSelectedNodeId(nodeId);
    window.setTimeout(() => {
      fitView({ nodes: [{ id: nodeId }], padding: 0.6, duration: 220 });
    }, 0);
  };

  const saveGraph = async (graphOverride?: AutomationGraphResponse): Promise<AutomationGraphResponse | null> => {
    const graphToSave = graphOverride ?? graph;
    if (!automationId || !graphToSave) return null;
    setSaving(true);
    setMutationError(null);
    try {
      const saved = await automationApiService.saveGraph(automationId, graphToSaveRequest(graphToSave));
      setGraph(saved);
      setDirty(false);
      return saved;
    } catch (err) {
      console.error("Error saving graph:", err);
      setMutationError(err instanceof Error ? err.message : "Failed to save graph.");
      return null;
    } finally {
      setSaving(false);
    }
  };

  const saveNodePatch = async (
    nodeId: string,
    patch: Partial<Pick<AutomationNode, "name" | "description" | "config">>
  ): Promise<void> => {
    if (!graph) return;
    const nextGraph = patchNode(graph, nodeId, patch);
    setGraph(nextGraph);
    setDirty(true);
    await saveGraph(nextGraph);
  };

  const openActionConfiguration = useCallback((nodeId: string, action: AutomationActionCatalogItem) => {
    if (!action.install_schema) {
      setMutationError(action.disabled_reason ?? "This action is not available.");
      return;
    }
    setConfiguringAction(action);
    setConfiguringActionNodeId(nodeId);
    setConfiguringActionError(null);
    setPanelMode("configure");
  }, []);

  const closeActionConfiguration = useCallback(() => {
    if (configuringActionSubmitting) return;
    setConfiguringAction(null);
    setConfiguringActionNodeId(null);
    setConfiguringActionError(null);
    setPanelMode("step");
  }, [configuringActionSubmitting]);

  const handleActionConfigurationSubmit = useCallback(async (data: Record<string, FormValue>) => {
    if (!automationId || !configuringAction || !configuringActionNodeId) return;
    setConfiguringActionSubmitting(true);
    setConfiguringActionError(null);
    try {
      const config = formValuesToConfig(data);
      const installed = await automationApiService.enableSkill(
        automationId,
        configuringAction.skill_id,
        { config },
      );
      const catalogData = await automationApiService.getActionCatalog(automationId);
      setActionCatalog(catalogData.actions);
      const nextAction =
        findCatalogActionForInstalledSkill(catalogData.actions, installed, configuringAction.action) ??
        {
          ...configuringAction,
          installed_skill_id: installed.installed_skill_id,
          available: true,
          configured: true,
          enabled: installed.enabled,
          disabled_reason: null,
        };
      updateGraph((current) => patchNode(current, configuringActionNodeId, {
        name: nextAction.label,
        config: {
          action_type: "skill_action",
          installed_skill_id: installed.installed_skill_id,
          skill_id: installed.skill_id,
          action: configuringAction.action,
          arguments: {},
        },
      }));
      setConfiguringAction(null);
      setConfiguringActionNodeId(null);
      setConfiguringActionError(null);
      setPanelMode("step");
    } catch (err) {
      console.error("Error configuring automation action:", err);
      setConfiguringActionError(err instanceof Error ? err.message : "Failed to configure action.");
    } finally {
      setConfiguringActionSubmitting(false);
    }
  }, [
    automationId,
    configuringAction,
    configuringActionNodeId,
    updateGraph,
  ]);

  const copySmartValue = useCallback(async (value: string) => {
    try {
      await copyToClipboard(value);
      setCopiedSmartValue(value);
      window.setTimeout(() => setCopiedSmartValue((current) => (current === value ? null : current)), 1400);
    } catch (err) {
      console.error("Error copying smart value:", err);
    }
  }, []);

  const updateAutomationStatus = async () => {
    if (!automationId) return;
    const nextStatus = automation.status === "active" ? "disabled" : "active";
    setSaving(true);
    setMutationError(null);
    try {
      if (dirty) {
        const saved = await saveGraph();
        if (!saved) return;
      }
      await automationApiService.updateAutomation(automationId, { status: nextStatus });
      await reloadAutomation();
    } catch (err) {
      console.error("Error updating automation status:", err);
      setMutationError(err instanceof Error ? err.message : "Failed to update automation status.");
    } finally {
      setSaving(false);
    }
  };

  const removeAutomation = async () => {
    if (!automationId) return;
    setSaving(true);
    try {
      await automationApiService.deleteAutomation(automationId);
      navigate("/dashboard/automations");
    } catch (err) {
      console.error("Error deleting automation:", err);
      setMutationError(err instanceof Error ? err.message : "Failed to delete automation.");
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    if (!automationId) return;
    const pollId = activeRunPollId.current + 1;
    activeRunPollId.current = pollId;
    setRunning(true);
    setMutationError(null);
    setRunInputError(null);
    setLatestRun(null);
    try {
      const parsed = JSON.parse(runInput) as Record<string, unknown>;
      if (dirty) {
        const saved = await saveGraph();
        if (!saved) return;
      }
      const run = await automationApiService.testRun(automationId, { input: parsed });
      let detail = await automationApiService.getRun(automationId, run.run_id);
      while (activeRunPollId.current === pollId) {
        setLatestRun(detail);
        if (TERMINAL_RUN_STATUSES.has(detail.run.status)) {
          break;
        }
        await sleep(RUN_POLL_INTERVAL_MS);
        detail = await automationApiService.getRun(automationId, run.run_id);
      }
    } catch (err) {
      console.error("Error running automation:", err);
      if (err instanceof SyntaxError) {
        setRunInputError(err.message);
      } else {
        setMutationError(err instanceof Error ? err.message : "Failed to run automation.");
      }
    } finally {
      if (activeRunPollId.current === pollId) {
        setRunning(false);
      }
    }
  };

  if (loading) return <LoadingState />;
  if (error || !graph) return <ErrorState message={error ?? "Failed to load builder."} onRetry={loadGraph} />;

  return (
    <div className="automation-builder">
      <div className="automation-builder__toolbar">
        <div>
          <p className="automation-builder__eyebrow">Builder</p>
          <h1>{automation.title}</h1>
        </div>
        <div className="automation-builder__toolbar-actions">
          <StatusBadge status={automation.status === "active" ? "active" : "inactive"} label={automation.status} />
          <Button variant={panelMode === "test" ? "default" : "outline"} size="sm" onClick={() => setPanelMode("test")}>
            <Play className="h-4 w-4" />
            Test Run
          </Button>
          <Button size="sm" onClick={() => void saveGraph()} disabled={saving || !dirty}>
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : dirty ? "Save" : "Saved"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => void updateAutomationStatus()} disabled={saving}>
            {automation.status === "active" ? "Disable" : "Activate"}
          </Button>
          <Button variant="destructive" size="sm" onClick={() => void removeAutomation()} disabled={saving}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {mutationError && (
        <div className="automation-builder__error">{mutationError}</div>
      )}

      <div className="automation-builder__body">
        <div className="automation-builder__workspace">
          <aside className={`automation-builder__side-panel automation-builder__side-panel--${panelMode}`}>
            <div className="automation-builder__panel-tabs">
              <Button size="sm" variant={panelMode === "step" ? "default" : "ghost"} onClick={() => setPanelMode("step")}>
                Step
              </Button>
              <Button size="sm" variant={panelMode === "smart" ? "default" : "ghost"} onClick={() => setPanelMode("smart")}>
                <Lightbulb className="h-4 w-4" />
                Smart
              </Button>
              <Button size="sm" variant={panelMode === "test" ? "default" : "ghost"} onClick={() => setPanelMode("test")}>
                <Play className="h-4 w-4" />
                Test
              </Button>
            </div>
            {panelMode === "test" ? (
              <div className="automation-builder__panel-content">
                <AutomationRunPanel
                  input={runInput}
                  inputError={runInputError}
                  running={running}
                  latestRun={latestRun}
                  onInputChange={(value) => {
                    setRunInput(value);
                    setRunInputError(null);
                  }}
                  onFormatInput={() => {
                    const formatted = formatJsonText(runInput);
                    setRunInput(formatted.value);
                    setRunInputError(formatted.error);
                  }}
                  onRun={() => void runTest()}
                  onClose={() => setPanelMode("step")}
                />
              </div>
            ) : panelMode === "smart" ? (
              <div className="automation-builder__panel-content">
                <SmartValueHelper
                  examples={smartValueExamples}
                  copiedValue={copiedSmartValue}
                  onCopy={(value) => void copySmartValue(value)}
                />
              </div>
            ) : panelMode === "configure" && configuringAction?.install_schema ? (
              <div className="automation-builder__panel-content">
                <div className="automation-builder__panel-header">
                  <div>
                    <h2>Configure Action</h2>
                    <p>{configuringAction.label}</p>
                  </div>
                  <Button variant="ghost" size="icon" onClick={closeActionConfiguration} disabled={configuringActionSubmitting}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
                {configuringActionError && (
                  <div className="automation-builder__error">{configuringActionError}</div>
                )}
                <SchemaForm
                  schema={configuringAction.install_schema}
                  onSubmit={handleActionConfigurationSubmit}
                  onCancel={closeActionConfiguration}
                  submitLabel="Configure"
                  isLoading={configuringActionSubmitting}
                />
              </div>
            ) : (
              <AutomationInspector
                node={selectedNode}
                steps={editableSteps}
                agents={agents}
                actionCatalog={actionCatalog}
                onAddStep={addStep}
                onSelectNode={setSelectedNodeId}
                onPlaceNode={placeNodeOnCanvas}
                onClose={() => {
                  setSelectedNodeId(null);
                  setPanelMode("step");
                }}
                onOpenSmartValues={() => setPanelMode("smart")}
                onChange={(nodeId, patch) => updateGraph((current) => patchNode(current, nodeId, patch))}
                onSaveChange={saveNodePatch}
                onTypeChange={(nodeId, type) => updateGraph((current) => updateStepType(current, nodeId, type))}
                onDelete={(nodeId) => {
                  setSelectedNodeId(null);
                  updateGraph((current) => deleteNode(current, nodeId));
                }}
                onConfigureAction={openActionConfiguration}
              />
            )}
          </aside>

          <div className="automation-builder__canvas">
            <div className="automation-builder__canvas-rail">
              <Button size="sm" onClick={addStep} title="Add step">
                <Plus className="h-4 w-4" />
                Add Step
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  const firstEditable = editableSteps[0];
                  setSelectedNodeId(firstEditable?.node_id ?? graph.nodes.find((node) => node.type === "start")?.node_id ?? null);
                  setPanelMode("smart");
                }}
                title="Open smart values"
              >
                <Lightbulb className="h-4 w-4" />
                Smart Values
              </Button>
            </div>
            {selectedEdge && (
              <div className="automation-builder__edge-actions">
                <div>
                  <span>Selected edge</span>
                  <strong>{selectedEdge.label}</strong>
                </div>
                <Button variant="destructive" size="sm" onClick={removeSelectedEdge}>
                  <Trash2 className="h-4 w-4" />
                  Delete
                </Button>
              </div>
            )}
            {editableSteps.length === 0 && (
              <div className="automation-builder__empty-canvas">
                <Workflow className="h-10 w-10" />
                <div>
                  <p>No steps yet</p>
                  <span>Add the first editable workflow step. Start and Done are managed automatically.</span>
                </div>
                <Button onClick={addStep}>
                  <Plus className="h-4 w-4" />
                  Add First Step
                </Button>
              </div>
            )}
            <ReactFlow
              nodes={flowNodes}
              edges={flowEdges}
              nodeTypes={nodeTypes}
              onNodesChange={handleNodesChange}
              onEdgesChange={handleEdgesChange}
              onConnect={handleConnect}
              nodesDraggable
              onNodeDragStop={(_, node) => commitNodePosition(node.id, node.position)}
              onNodeClick={(_, node) => {
                setSelectedEdgeId(null);
                setSelectedNodeId(node.id);
                setPanelMode("step");
              }}
              onEdgeClick={(_, edge) => {
                setSelectedNodeId(null);
                setSelectedEdgeId(edge.id);
              }}
              onPaneClick={() => {
                setSelectedNodeId(null);
                setSelectedEdgeId(null);
                if (panelMode === "configure") return;
                setPanelMode("step");
              }}
              fitView
            >
              <Background />
              <Controls />
            </ReactFlow>
          </div>
        </div>
      </div>

    </div>
  );
}

interface AutomationInspectorProps {
  node: AutomationNode | null;
  steps: AutomationNode[];
  agents: AgentResponse[];
  actionCatalog: AutomationActionCatalogItem[];
  onAddStep: () => void;
  onSelectNode: (nodeId: string) => void;
  onPlaceNode: (nodeId: string) => void;
  onClose: () => void;
  onOpenSmartValues: () => void;
  onChange: (
    nodeId: string,
    patch: Partial<Pick<AutomationNode, "name" | "description" | "config">>
  ) => void;
  onSaveChange: (
    nodeId: string,
    patch: Partial<Pick<AutomationNode, "name" | "description" | "config">>
  ) => Promise<void>;
  onTypeChange: (nodeId: string, type: "action" | "condition") => void;
  onDelete: (nodeId: string) => void;
  onConfigureAction: (nodeId: string, action: AutomationActionCatalogItem) => void;
}

function AutomationRunPanel({
  input,
  inputError,
  running,
  latestRun,
  onInputChange,
  onFormatInput,
  onRun,
  onClose,
}: {
  input: string;
  inputError: string | null;
  running: boolean;
  latestRun: AutomationRunDetailResponse | null;
  onInputChange: (value: string) => void;
  onFormatInput: () => void;
  onRun: () => void;
  onClose: () => void;
}) {
  return (
    <div className="automation-run-panel">
      <div className="automation-run-panel__header">
        <div>
          <h2>Test run</h2>
          <p>Unsaved graph changes are saved before execution.</p>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} disabled={running}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <AutomationJsonEditor
        label="Manual input"
        value={input}
        error={inputError}
        minHeight="8rem"
        onChange={onInputChange}
        onFormat={onFormatInput}
      />

      <div className="automation-run-panel__actions">
        <Button onClick={onRun} disabled={running}>
          <Play className="h-4 w-4" />
          {running ? "Running..." : "Run test"}
        </Button>
      </div>

      <div className="automation-run-log">
        <div className="automation-run-log__header">
          <span>Step log</span>
          {latestRun && (
            <StatusBadge
              status={automationRunBadgeStatus(latestRun.run.status)}
              label={latestRun.run.status}
            />
          )}
        </div>
        {running && (
          <div className="automation-run-log__loading">
            <div className="automation-run-log__spinner" />
            <span>Running automation...</span>
          </div>
        )}
        {latestRun ? (
          <div className="automation-run-log__steps">
            {latestRun.node_results.map((result) => (
              <div className="automation-run-log__step" key={result.result_id}>
                <div>
                  <strong>{result.node_id}</strong>
                  <small>{result.error ?? result.status}</small>
                </div>
                <StatusBadge
                  status={automationRunBadgeStatus(result.status)}
                  label={result.status}
                />
              </div>
            ))}
          </div>
        ) : !running ? (
          <div className="automation-run-log__empty">Run the automation to see step results here.</div>
        ) : (
          <div className="automation-run-log__empty">Waiting for the first step result.</div>
        )}
      </div>

      {latestRun && (
        <AutomationJsonTreeViewer
          label="Run context"
          value={filterRuntimeLogContext(latestRun.context)}
        />
      )}
    </div>
  );
}

interface SmartValueExample {
  label: string;
  value: string;
  description: string;
}

function SmartValueHelper({
  examples,
  copiedValue,
  onCopy,
}: {
  examples: SmartValueExample[];
  copiedValue: string | null;
  onCopy: (value: string) => void;
}) {
  return (
    <div className="automation-smart-values">
      <div className="automation-smart-values__title">Smart values</div>
      <p>Copy a value and paste it into a prompt template or condition.</p>
      <div className="automation-smart-values__list">
        {examples.map((example) => (
          <button
            key={`${example.label}-${example.value}`}
            type="button"
            className="automation-smart-values__item"
            onClick={() => onCopy(example.value)}
          >
            <span>
              <strong>{example.label}</strong>
              <small>{example.description}</small>
              <code>{example.value}</code>
            </span>
            {copiedValue === example.value ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function AutomationInspector({
  node,
  steps,
  agents,
  actionCatalog,
  onAddStep,
  onSelectNode,
  onPlaceNode,
  onClose,
  onOpenSmartValues,
  onChange,
  onSaveChange,
  onTypeChange,
  onDelete,
  onConfigureAction,
}: AutomationInspectorProps) {
  if (!node) {
    return (
      <aside className="automation-inspector">
        <div className="automation-inspector__header">
          <h2>Workflow</h2>
          <Button variant="ghost" size="icon" onClick={onClose} title="Close panel">
            <X className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenSmartValues}
            title="Smart value examples"
          >
            <Lightbulb className="h-4 w-4" />
          </Button>
        </div>
        {steps.length === 0 ? (
          <>
            <p>Add the first step to place an editable node on the canvas.</p>
            <Button className="mt-4" onClick={onAddStep}>
              <Plus className="h-4 w-4" />
              Add First Step
            </Button>
          </>
        ) : (
          <>
            <p>Select a step to configure it.</p>
            <div className="automation-inspector__step-list">
              {steps.map((step) => (
                <button key={step.node_id} type="button" onClick={() => onSelectNode(step.node_id)}>
                  <span>{step.name}</span>
                  <small>{step.type === "condition" ? "IF/ELSE" : "Action"}</small>
                </button>
              ))}
            </div>
            <Button className="mt-4" variant="outline" onClick={onAddStep}>
              <Plus className="h-4 w-4" />
              Add Step
            </Button>
          </>
        )}
      </aside>
    );
  }

  const skillConfig = node.type === "action" ? getSkillActionConfig(node.config) : null;
  const selectedAction = skillConfig
    ? actionCatalog.find((item) => catalogActionKey(item) === skillActionKey(skillConfig)) ??
      actionCatalog.find((item) => catalogActionKey(item) === DEFAULT_SKILL_ACTION) ??
      null
    : null;
  const actionForm = selectedAction?.action_form
    ? hydrateActionForm(selectedAction.action_form, agents)
    : null;
  const expression = typeof node.config.expression === "string" ? node.config.expression : "";
  const isSystemNode = node.type === "start" || node.type === "final";

  return (
    <aside className="automation-inspector">
      <div className="automation-inspector__header">
        <h2>Step</h2>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={onOpenSmartValues}
            title="Smart value examples"
          >
            <Lightbulb className="h-4 w-4" />
          </Button>
          {node.type !== "start" && node.type !== "final" && (
            <Button variant="ghost" size="icon" onClick={() => onDelete(node.node_id)}>
              <Trash2 className="h-4 w-4 text-red-400" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onClose} title="Close panel">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {!isSystemNode && (
        <Button className="automation-inspector__place-button" onClick={() => onPlaceNode(node.node_id)}>
          Place on canvas
        </Button>
      )}
      {isSystemNode && (
        <div className="automation-inspector__notice">
          This is a system step. Use <strong>Add Step</strong> to create an editable workflow step.
        </div>
      )}
      <div className="space-y-4">
        <div className="space-y-2">
          <Label>Step type</Label>
          <Select
            value={node.type === "condition" ? "condition" : "action"}
            onValueChange={(value) => onTypeChange(node.node_id, value as "action" | "condition")}
            disabled={isSystemNode}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="action">Action</SelectItem>
              <SelectItem value="condition">IF/ELSE</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {node.type === "action" && (
          <div className="space-y-2">
            <Label>Action</Label>
            <Select
              value={skillConfig ? skillActionKey(skillConfig) : DEFAULT_SKILL_ACTION}
              onValueChange={(value) => {
                const catalogItem = actionCatalog.find((item) => catalogActionKey(item) === value);
                if (!catalogItem) return;
                if (!catalogItem.available) {
                  onConfigureAction(node.node_id, catalogItem);
                  return;
                }
                onChange(node.node_id, {
                  config: {
                    action_type: "skill_action",
                    installed_skill_id: catalogItem.installed_skill_id,
                    skill_id: catalogItem.skill_id,
                    action: catalogItem.action,
                    arguments: {},
                  },
                  name: catalogItem?.label ?? node.name,
                });
              }}
              disabled={isSystemNode || actionCatalog.length === 0}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select action" />
              </SelectTrigger>
              <SelectContent>
                {actionCatalog.map((item) => (
                  <SelectItem
                    key={catalogActionKey(item)}
                    value={catalogActionKey(item)}
                    disabled={!item.available && !item.install_schema}
                  >
                    {item.disabled_reason ? `${item.label} (${item.disabled_reason})` : item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="node-name">Name</Label>
          <Input
            id="node-name"
            value={node.name}
            onChange={(event) => onChange(node.node_id, { name: event.target.value })}
            disabled={isSystemNode}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="node-description">Description</Label>
          <Textarea
            id="node-description"
            value={node.description ?? ""}
            onChange={(event) => onChange(node.node_id, { description: event.target.value })}
            disabled={isSystemNode}
          />
        </div>

        {skillConfig && selectedAction && (
          <>
            {actionForm ? (
              <SchemaForm
                key={`${node.node_id}:${skillActionKey(skillConfig)}`}
                schema={actionForm}
                initialValues={argumentsToFormValues(skillConfig.arguments)}
                submitLabel="Apply Arguments"
                onSubmit={(values) =>
                  onSaveChange(node.node_id, {
                    config: {
                      ...skillConfig,
                      arguments: formValuesToArguments(values, selectedAction.input_schema),
                    },
                  })
                }
              />
            ) : (
              <AutomationJsonEditor
                label="Arguments"
                value={JSON.stringify(skillConfig.arguments, null, 2)}
                onChange={(argumentsValue) => {
                  try {
                    const parsed = JSON.parse(argumentsValue) as Record<string, unknown>;
                    onChange(node.node_id, {
                      config: { ...skillConfig, arguments: parsed },
                    });
                  } catch {
                    // Keep invalid draft text local to the textarea until it parses.
                  }
                }}
              />
            )}
          </>
        )}

        {node.type === "condition" && (
          <div className="space-y-2">
            <Label htmlFor="condition-expression">Condition expression</Label>
            <Input
              id="condition-expression"
              value={expression}
              onChange={(event) =>
                onChange(node.node_id, {
                  config: {
                    expression: event.target.value,
                    true_label: "true",
                    false_label: "false",
                  },
                })
              }
            />
            <p className="text-xs text-[var(--text-muted)]">
              Supports truthy JSONPath plus simple == and != comparisons. Use the bulb for node paths.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
