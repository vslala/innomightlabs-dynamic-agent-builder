/**
 * An automation that lives only in the browser, for the docs tutorial.
 *
 * It supplies the same draft, runs, params, gateway, and operations the
 * dashboard page builds from the API, so the real `AutomationWorkspace` renders
 * unchanged. Nothing is saved, and test runs are simulated: smart values are
 * rendered the way the runner renders them, and each action returns the sample
 * result from `SIMULATED_ACTIONS`.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";

import type {
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationRunDetailResponse,
  AutomationRunNodeResult,
  AutomationRunResponse,
  AutomationTrigger,
  CreateAutomationTriggerRequest,
} from "../../../types/automation";
import type { WorkspaceOperations } from "../../dashboard/automations/AutomationWorkspace";
import { linearize } from "../../dashboard/automations/chain/chainModel";
import { patchStep, type GraphMutation } from "../../dashboard/automations/chain/chainOperations";
import { errorCount, validateChain } from "../../dashboard/automations/chain/chainValidation";
import { parseCondition } from "../../dashboard/automations/chain/conditionExpression";
import { resolvePath } from "../../dashboard/automations/chain/smartValues";
import type { ChainGateway } from "../../dashboard/automations/components/chainGateway";
import type { AutomationDraft } from "../../dashboard/automations/hooks/useAutomationDraft";
import type { AutomationRunsState } from "../../dashboard/automations/hooks/useAutomationRuns";
import {
  applyParamPatch,
  type WorkspaceParams,
} from "../../dashboard/automations/hooks/useWorkspaceParams";
import {
  installedSendEmail,
  SAMPLE_RECIPIENT,
  SEND_EMAIL_INSTALLED_ID,
  SIMULATED_ACTIONS,
  TRIGGER_FORMS,
  tutorialCatalog,
  tutorialGraph,
  type TutorialStage,
} from "./tutorialFixtures";

const STEP_DELAY_MS = 700;

export interface SandboxAutomation {
  draft: AutomationDraft;
  runs: AutomationRunsState;
  params: WorkspaceParams;
  gateway: ChainGateway;
  operations: WorkspaceOperations;
  graph: AutomationGraphResponse;
}

export function useSandboxAutomation(stage: TutorialStage, expandedNodeId: string | null): SandboxAutomation {
  const [graph, setGraph] = useState(() => tutorialGraph(stage));
  const [catalog, setCatalog] = useState(() => tutorialCatalog(stage !== "created" && stage !== "agent"));
  const skillConfigs = useRef<Record<string, Record<string, unknown>>>({
    [SEND_EMAIL_INSTALLED_ID]: { to: SAMPLE_RECIPIENT },
  });
  const params = useLocalParams(expandedNodeId);
  const runs = useSimulatedRuns(graph, skillConfigs);

  const chain = useMemo(() => linearize(graph), [graph]);
  const issues = useMemo(() => validateChain(graph, chain, catalog), [graph, chain, catalog]);

  const draft = useMemo<AutomationDraft>(
    () => ({
      graph,
      chain,
      catalog,
      issues,
      loading: false,
      loadError: null,
      saveState: "saved",
      saveError: null,
      apply: (mutation: GraphMutation) => setGraph(mutation.graph),
      patchNode: (nodeId, patch) => setGraph((current) => patchStep(current, nodeId, patch).graph),
      flush: async () => true,
      retry: () => undefined,
      reload: async () => undefined,
      refreshGraph: async () => undefined,
      reloadCatalog: async () => undefined,
    }),
    [catalog, chain, graph, issues]
  );

  const setTriggers = useCallback(
    (update: (triggers: AutomationTrigger[]) => AutomationTrigger[]) =>
      setGraph((current) => ({ ...current, triggers: update(current.triggers) })),
    []
  );

  const gateway = useMemo<ChainGateway>(
    () => ({
      previewSmartValues: async (template) => renderText(template, runs.context ?? {}),
      getTriggerForm: async (type) => {
        const form = TRIGGER_FORMS[type];
        if (!form) throw new Error(`There is no ${type} trigger form.`);
        return form;
      },
      createTrigger: async (request) =>
        setTriggers((triggers) => [...triggers, triggerFrom(request, graph.automation.automation_id)]),
      updateTrigger: async (triggerId, request) =>
        setTriggers((triggers) =>
          triggers.map((item) =>
            item.trigger_id === triggerId ? { ...item, ...request, config: request.config ?? item.config } : item
          )
        ),
      deleteTrigger: async (triggerId) =>
        setTriggers((triggers) => triggers.filter((item) => item.trigger_id !== triggerId)),
    }),
    [graph.automation.automation_id, runs.context, setTriggers]
  );

  const operations = useMemo<WorkspaceOperations>(
    () => ({
      changeStatus: async (status) => {
        // The server validates strictly before it lets an automation go live.
        if (status === "active" && errorCount(issues) > 0) {
          throw new Error(issues.find((issue) => issue.severity === "error")?.message);
        }
        setGraph((current) => ({ ...current, automation: { ...current.automation, status } }));
      },
      rename: async (title) =>
        setGraph((current) => ({ ...current, automation: { ...current.automation, title } })),
      deleteAutomation: async () => {
        throw new Error("This is a tutorial sandbox, so there is nothing to delete.");
      },
      publish: () => undefined,
      enableSkill: async (skillId, config) => {
        const installedSkillId = `${skillId}:sandbox`;
        skillConfigs.current[installedSkillId] = config;
        setCatalog((items) =>
          items.map((item) =>
            item.skill_id === skillId && skillId === "send_email" ? installedSendEmail(installedSkillId) : item
          )
        );
        return { installed_skill_id: installedSkillId, skill_id: skillId };
      },
    }),
    [issues]
  );

  return { draft, runs, params, gateway, operations, graph };
}

function useLocalParams(initialStep: string | null): WorkspaceParams {
  const [search, setSearch] = useState(
    () => new URLSearchParams(initialStep ? { step: initialStep } : {})
  );
  const update = useCallback(
    (patch: Parameters<WorkspaceParams["update"]>[0]) =>
      setSearch((current) => applyParamPatch(current, patch) ?? current),
    []
  );
  return useMemo(
    () => ({
      step: search.get("step"),
      panel: search.get("panel"),
      run: search.get("run"),
      focus: search.get("focus"),
      update,
    }),
    [search, update]
  );
}

function useSimulatedRuns(
  graph: AutomationGraphResponse,
  skillConfigs: RefObject<Record<string, Record<string, unknown>>>
): AutomationRunsState {
  const [details, setDetails] = useState<AutomationRunDetailResponse[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const graphRef = useRef(graph);

  useEffect(() => {
    graphRef.current = graph;
  }, [graph]);

  useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);

  const startTestRun = useCallback(
    async (input: Record<string, unknown>) => {
      const frames = simulateRun(graphRef.current, input, skillConfigs.current ?? {});
      // Reveal the run one step at a time, the way polling a real run does.
      frames.forEach((frame, index) => {
        const timer = window.setTimeout(() => {
          setDetails((current) => [frame, ...current.filter((item) => item.run.run_id !== frame.run.run_id)]);
        }, index * STEP_DELAY_MS);
        timers.current.push(timer);
      });
      return frames[0].run;
    },
    [skillConfigs]
  );

  const detail = details.find((item) => item.run.run_id === selectedRunId) ?? null;
  const resultsByNodeId = useMemo(
    () => new Map((detail?.node_results ?? []).map((result) => [result.node_id, result])),
    [detail]
  );

  return {
    runs: details.map((item) => item.run),
    hasMore: false,
    loadingRuns: false,
    loadingMore: false,
    runsError: null,
    selectedRunId,
    detail,
    detailLoading: false,
    resultsByNodeId,
    context: detail?.context ?? null,
    isRunning: details.some((item) => item.run.status === "running"),
    startError: null,
    loadRuns: async () => undefined,
    loadMore: async () => undefined,
    selectRun: setSelectedRunId,
    startTestRun,
  };
}

/** Every intermediate state of one run, from "just started" to its final result. */
function simulateRun(
  graph: AutomationGraphResponse,
  input: Record<string, unknown>,
  skillConfigs: Record<string, Record<string, unknown>>
): AutomationRunDetailResponse[] {
  const runId = `run-${crypto.randomUUID()}`;
  const startedAt = new Date().toISOString();
  const trigger = graph.triggers.find((item) => item.type === "manual" && item.enabled) ?? graph.triggers[0];
  const run: AutomationRunResponse = {
    run_id: runId,
    automation_id: graph.automation.automation_id,
    trigger_id: trigger?.trigger_id ?? null,
    status: "running",
    created_by: SAMPLE_RECIPIENT,
    created_at: startedAt,
    started_at: startedAt,
  };
  const context: Record<string, unknown> = {
    input,
    trigger: { type: "manual", trigger_id: trigger?.trigger_id ?? null },
    nodes: {},
    steps: {},
    execution: {},
  };
  const results: AutomationRunNodeResult[] = [];
  const frames: AutomationRunDetailResponse[] = [snapshot(run, context, results)];

  let current = graph.nodes.find((item) => item.type === "start");
  while (current) {
    const { output, error, label } = executeNode(current, context, skillConfigs);
    const status = error ? "failed" : "succeeded";
    results.push({
      result_id: `${runId}:${current.node_id}`,
      run_id: runId,
      automation_id: run.automation_id,
      node_id: current.node_id,
      status,
      input: current.type === "action" ? renderValue(argumentsOf(current), context) as Record<string, unknown> : {},
      output,
      error,
      message_ids: {},
      started_at: new Date().toISOString(),
      completed_at: new Date().toISOString(),
    });
    recordStep(context, current, status, output, error);

    if (error) {
      frames.push(snapshot({ ...run, status: "failed", error, completed_at: new Date().toISOString() }, context, results));
      return frames;
    }
    frames.push(snapshot(run, context, results));
    current = nextNode(graph.edges, graph.nodes, current.node_id, label);
  }

  frames.push(snapshot({ ...run, status: "succeeded", completed_at: new Date().toISOString() }, context, results));
  return frames;
}

function executeNode(
  node: AutomationNode,
  context: Record<string, unknown>,
  skillConfigs: Record<string, Record<string, unknown>>
): { output: Record<string, unknown>; error: string | null; label: string } {
  if (node.type === "start") return { output: context.input as Record<string, unknown>, error: null, label: "next" };
  if (node.type === "final") return { output: {}, error: null, label: "next" };
  if (node.type === "condition") {
    const result = evaluateCondition(String(node.config.expression ?? ""), context);
    return { output: { result }, error: null, label: result ? "true" : "false" };
  }

  const config = node.config as Record<string, unknown>;
  const skillId = String(config.skill_id ?? "");
  const action = String(config.action ?? "");
  const simulate = SIMULATED_ACTIONS[`${skillId}.${action}`];
  if (!simulate) {
    return { output: {}, error: "The tutorial only simulates Invoke Agent and Send Email.", label: "next" };
  }
  const rendered = renderValue(argumentsOf(node), context) as Record<string, unknown>;
  const installedSkillId = String(config.installed_skill_id ?? skillId);
  return {
    output: {
      installed_skill_id: installedSkillId,
      skill_id: skillId,
      action,
      arguments: rendered,
      result: simulate(rendered, skillConfigs[installedSkillId] ?? {}),
    },
    error: null,
    label: "next",
  };
}

function recordStep(
  context: Record<string, unknown>,
  node: AutomationNode,
  status: string,
  output: Record<string, unknown>,
  error: string | null
) {
  (context.nodes as Record<string, unknown>)[node.node_id] = { status, output, message_ids: {}, error };
  if (node.alias) {
    (context.steps as Record<string, unknown>)[node.alias] = {
      node_id: node.node_id,
      name: node.name,
      type: node.type,
    };
  }
  context.execution = { last_node_id: node.node_id, last_step_alias: node.alias ?? null };
}

function nextNode(
  edges: AutomationEdge[],
  nodes: AutomationNode[],
  fromNodeId: string,
  label: string
): AutomationNode | undefined {
  const edge = edges.find((item) => item.source_node_id === fromNodeId && item.label === label);
  return edge ? nodes.find((item) => item.node_id === edge.target_node_id) : undefined;
}

function evaluateCondition(expression: string, context: Record<string, unknown>): boolean {
  const parsed = parseCondition(expression);
  if (parsed.kind === "raw") return false;
  const left = resolvePath(context, parsed.left);
  if (parsed.operator === "truthy") return Boolean(left);
  const equal = String(left ?? "") === parsed.right;
  return parsed.operator === "eq" ? equal : !equal;
}

function argumentsOf(node: AutomationNode): Record<string, unknown> {
  const args = (node.config as Record<string, unknown>).arguments;
  return args && typeof args === "object" ? (args as Record<string, unknown>) : {};
}

function snapshot(
  run: AutomationRunResponse,
  context: Record<string, unknown>,
  results: AutomationRunNodeResult[]
): AutomationRunDetailResponse {
  return { run: { ...run }, context: structuredClone(context), node_results: [...results] };
}

const TOKEN = /{{\s*([^}|]+?)\s*(?:\|[^}]*)?}}/g;

/** Mirrors the runner: a lone token keeps its type, anything else becomes text. */
function renderValue(value: unknown, context: Record<string, unknown>): unknown {
  if (typeof value === "string") {
    const lone = value.trim().match(/^{{\s*([^}|]+?)\s*(?:\|[^}]*)?}}$/);
    return lone ? resolvePath(context, normalisePath(lone[1])) ?? "" : renderText(value, context);
  }
  if (Array.isArray(value)) return value.map((item) => renderValue(item, context));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, renderValue(item, context)])
    );
  }
  return value;
}

function renderText(template: string, context: Record<string, unknown>): string {
  return template.replace(TOKEN, (_match, path: string) => {
    const resolved = resolvePath(context, normalisePath(path));
    if (resolved === undefined || resolved === null) return "";
    return typeof resolved === "string" ? resolved : JSON.stringify(resolved);
  });
}

function normalisePath(path: string): string {
  return path.trim().replace(/^\$\./, "");
}

function triggerFrom(request: CreateAutomationTriggerRequest, automationId: string): AutomationTrigger {
  return {
    trigger_id: request.trigger_id ?? `trigger-${crypto.randomUUID()}`,
    automation_id: automationId,
    type: request.type,
    name: request.name,
    enabled: request.enabled ?? true,
    entry_node_id: request.entry_node_id,
    config: request.config ?? {},
    created_at: new Date().toISOString(),
  };
}
