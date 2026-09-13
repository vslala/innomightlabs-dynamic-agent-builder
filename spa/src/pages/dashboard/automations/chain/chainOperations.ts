/**
 * Pure graph mutations for the rule chain editor.
 *
 * Every operation preserves the invariants the backend validates in draft mode:
 * unique ids, exactly one start and final node, resolvable edge endpoints, no
 * dead ends, no unreachable nodes, and no cycles. Because the editor never draws
 * edges by hand, an invalid graph *shape* is unreachable through the UI.
 *
 * Each operation returns the next graph plus how it should be persisted:
 * a single-node PATCH for field edits, or an atomic whole-graph PUT for anything
 * that touches more than one entity.
 */

import type {
  AutomationActionCatalogItem,
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationNodeType,
} from "../../../../types/automation";
import { descendants, edgeFor, findJoin, groupOutgoing, topoOrder } from "./chainModel";

export type ChainStepType = "action" | "condition";

export interface NodePatch {
  name?: string;
  alias?: string | null;
  description?: string | null;
  config?: Record<string, unknown>;
}

export type PersistPlan =
  | { kind: "structural" }
  | { kind: "node"; nodeId: string; patch: NodePatch }
  | { kind: "none" };

export interface GraphMutation {
  graph: AutomationGraphResponse;
  persist: PersistPlan;
  /** Step the editor should expand and focus after the change. */
  focusNodeId?: string | null;
  /** Steps discarded by the change, so the UI can confirm before committing. */
  removedNodeIds: string[];
}

const NO_CHANGE = (graph: AutomationGraphResponse): GraphMutation => ({
  graph,
  persist: { kind: "none" },
  removedNodeIds: [],
});

export const DEFAULT_CONDITION_EXPRESSION = "";

export function createNodeId(type: AutomationNodeType | ChainStepType): string {
  return `${type}-${crypto.randomUUID()}`;
}

function createEdgeId(): string {
  return `edge-${crypto.randomUUID()}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function makeNode(
  graph: AutomationGraphResponse,
  type: ChainStepType,
  overrides: Partial<AutomationNode> = {}
): AutomationNode {
  return {
    node_id: createNodeId(type),
    automation_id: graph.automation.automation_id,
    type,
    name: type === "condition" ? "Condition" : "New step",
    alias: null,
    description: null,
    position: {},
    config: type === "condition" ? conditionConfig() : {},
    created_at: nowIso(),
    updated_at: null,
    ...overrides,
  };
}

function makeEdge(
  graph: AutomationGraphResponse,
  sourceNodeId: string,
  targetNodeId: string,
  label: string
): AutomationEdge {
  return {
    edge_id: createEdgeId(),
    automation_id: graph.automation.automation_id,
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
    label,
    condition: null,
    created_at: nowIso(),
    updated_at: null,
  };
}

export function conditionConfig(expression: string = DEFAULT_CONDITION_EXPRESSION) {
  return { expression, true_label: "true", false_label: "false" };
}

export function skillActionConfig(item: AutomationActionCatalogItem): Record<string, unknown> {
  return {
    action_type: "skill_action",
    installed_skill_id: item.installed_skill_id ?? null,
    skill_id: item.skill_id,
    action: item.action,
    arguments: {},
  };
}

function replaceEdge(
  graph: AutomationGraphResponse,
  edgeId: string,
  patch: Partial<AutomationEdge>
): AutomationGraphResponse {
  return {
    ...graph,
    edges: graph.edges.map((edge) => (edge.edge_id === edgeId ? { ...edge, ...patch } : edge)),
  };
}

/**
 * Splice a step into an existing connection.
 *
 * `A --label--> B` becomes `A --label--> N --next--> B`. A condition also gets a
 * `false` branch to B, so both lanes rejoin and neither is a dead end.
 */
export function insertStepOnEdge(
  graph: AutomationGraphResponse,
  edgeId: string,
  type: ChainStepType
): GraphMutation {
  const edge = graph.edges.find((item) => item.edge_id === edgeId);
  if (!edge) return NO_CHANGE(graph);

  const node = makeNode(graph, type);
  const target = edge.target_node_id;
  const tailEdges =
    type === "condition"
      ? [makeEdge(graph, node.node_id, target, "true"), makeEdge(graph, node.node_id, target, "false")]
      : [makeEdge(graph, node.node_id, target, "next")];

  const next: AutomationGraphResponse = {
    ...graph,
    nodes: [...graph.nodes, node],
    edges: [
      ...graph.edges.map((item) =>
        item.edge_id === edgeId ? { ...item, target_node_id: node.node_id } : item
      ),
      ...tailEdges,
    ],
  };

  return {
    graph: next,
    persist: { kind: "structural" },
    focusNodeId: node.node_id,
    removedNodeIds: [],
  };
}

/** Field-level edit: the only mutation that persists as a single-node PATCH. */
export function patchStep(
  graph: AutomationGraphResponse,
  nodeId: string,
  patch: NodePatch
): GraphMutation {
  const node = graph.nodes.find((item) => item.node_id === nodeId);
  if (!node) return NO_CHANGE(graph);
  return {
    graph: {
      ...graph,
      nodes: graph.nodes.map((item) => (item.node_id === nodeId ? { ...item, ...patch } : item)),
    },
    persist: { kind: "node", nodeId, patch },
    removedNodeIds: [],
  };
}

export function setStepAction(
  graph: AutomationGraphResponse,
  nodeId: string,
  item: AutomationActionCatalogItem
): GraphMutation {
  const node = graph.nodes.find((entry) => entry.node_id === nodeId);
  if (!node) return NO_CHANGE(graph);
  const shouldRename = !node.name || node.name === "New step" || node.name === "Condition";
  return patchStep(graph, nodeId, {
    config: skillActionConfig(item),
    ...(shouldRename ? { name: item.label } : {}),
  });
}

/**
 * Remove a step and close the gap.
 *
 * Every edge that pointed at the step is retargeted at what followed it, so the
 * predecessor keeps an outgoing edge and the tail stays reachable. Deleting a
 * condition keeps its `true` lane and discards the steps only the `false` lane
 * could reach.
 */
export function deleteStep(graph: AutomationGraphResponse, nodeId: string): GraphMutation {
  const node = graph.nodes.find((item) => item.node_id === nodeId);
  if (!node || node.type === "start" || node.type === "final") return NO_CHANGE(graph);

  const outgoing = groupOutgoing(graph.edges);
  const successor =
    node.type === "condition"
      ? edgeFor(outgoing, nodeId, "true")?.target_node_id ?? null
      : edgeFor(outgoing, nodeId, "next")?.target_node_id ?? null;
  if (!successor) return NO_CHANGE(graph);

  const removed = new Set<string>([nodeId, ...conditionOnlyNodeIds(graph, nodeId)]);
  const nodes = graph.nodes.filter((item) => !removed.has(item.node_id));
  const edges = graph.edges
    .filter((edge) => !removed.has(edge.source_node_id))
    .map((edge) => (removed.has(edge.target_node_id) ? { ...edge, target_node_id: successor } : edge));

  return {
    graph: { ...graph, nodes, edges: dedupeEdges(edges) },
    persist: { kind: "structural" },
    focusNodeId: null,
    removedNodeIds: [...removed],
  };
}

/** Steps that only the discarded `false` lane of a condition can reach. */
function conditionOnlyNodeIds(graph: AutomationGraphResponse, conditionNodeId: string): string[] {
  const node = graph.nodes.find((item) => item.node_id === conditionNodeId);
  if (!node || node.type !== "condition") return [];

  const outgoing = groupOutgoing(graph.edges);
  const trueEdge = edgeFor(outgoing, conditionNodeId, "true");
  const falseEdge = edgeFor(outgoing, conditionNodeId, "false");
  if (!trueEdge || !falseEdge) return [];

  const finalNodeId = graph.nodes.find((item) => item.type === "final")?.node_id ?? null;
  const join =
    findJoin(trueEdge.target_node_id, falseEdge.target_node_id, outgoing, topoOrder(graph)) ??
    finalNodeId;
  if (falseEdge.target_node_id === join) return [];

  const keep = descendants(trueEdge.target_node_id, outgoing, join);
  const boundary = join ?? undefined;
  return [...descendants(falseEdge.target_node_id, outgoing, boundary)].filter(
    (id) => id !== join && !keep.has(id) && id !== finalNodeId
  );
}

function dedupeEdges(edges: AutomationEdge[]): AutomationEdge[] {
  const seen = new Set<string>();
  return edges.filter((edge) => {
    const key = `${edge.source_node_id}->${edge.target_node_id}#${edge.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Reorder is allowed only between two adjacent plain steps, so branches stay intact. */
export function canMoveStep(
  graph: AutomationGraphResponse,
  nodeId: string,
  direction: "up" | "down"
): boolean {
  return movePlan(graph, nodeId, direction) !== null;
}

export function moveStep(
  graph: AutomationGraphResponse,
  nodeId: string,
  direction: "up" | "down"
): GraphMutation {
  const plan = movePlan(graph, nodeId, direction);
  if (!plan) return NO_CHANGE(graph);

  const { entryEdge, firstEdge, secondEdge, first, second } = plan;
  let next = replaceEdge(graph, entryEdge.edge_id, { target_node_id: second });
  next = replaceEdge(next, firstEdge.edge_id, {
    source_node_id: second,
    target_node_id: first,
  });
  next = replaceEdge(next, secondEdge.edge_id, {
    source_node_id: first,
    target_node_id: secondEdge.target_node_id,
  });

  return {
    graph: next,
    persist: { kind: "structural" },
    focusNodeId: nodeId,
    removedNodeIds: [],
  };
}

interface MovePlan {
  entryEdge: AutomationEdge;
  firstEdge: AutomationEdge;
  secondEdge: AutomationEdge;
  first: string;
  second: string;
}

function movePlan(
  graph: AutomationGraphResponse,
  nodeId: string,
  direction: "up" | "down"
): MovePlan | null {
  const outgoing = groupOutgoing(graph.edges);
  const nodeById = new Map(graph.nodes.map((node) => [node.node_id, node]));
  const isPlainStep = (id: string | undefined | null) =>
    Boolean(id && nodeById.get(id)?.type === "action");

  if (!isPlainStep(nodeId)) return null;

  const incomingEdges = graph.edges.filter((edge) => edge.target_node_id === nodeId);
  if (incomingEdges.length !== 1) return null;

  if (direction === "down") {
    const firstEdge = edgeFor(outgoing, nodeId, "next");
    const second = firstEdge?.target_node_id;
    if (!firstEdge || !isPlainStep(second)) return null;
    const secondIncoming = graph.edges.filter((edge) => edge.target_node_id === second);
    if (secondIncoming.length !== 1) return null;
    const secondEdge = edgeFor(outgoing, second as string, "next");
    if (!secondEdge) return null;
    return {
      entryEdge: incomingEdges[0],
      firstEdge,
      secondEdge,
      first: nodeId,
      second: second as string,
    };
  }

  const previousId = incomingEdges[0].source_node_id;
  if (!isPlainStep(previousId)) return null;
  const previousIncoming = graph.edges.filter((edge) => edge.target_node_id === previousId);
  if (previousIncoming.length !== 1) return null;
  const firstEdge = edgeFor(outgoing, previousId, "next");
  const secondEdge = edgeFor(outgoing, nodeId, "next");
  if (!firstEdge || !secondEdge) return null;
  return {
    entryEdge: previousIncoming[0],
    firstEdge,
    secondEdge,
    first: previousId,
    second: nodeId,
  };
}

/** Switch a step between an action and an IF/ELSE, rewiring its branches. */
export function convertStepType(
  graph: AutomationGraphResponse,
  nodeId: string,
  type: ChainStepType
): GraphMutation {
  const node = graph.nodes.find((item) => item.node_id === nodeId);
  if (!node || node.type === type || (node.type !== "action" && node.type !== "condition")) {
    return NO_CHANGE(graph);
  }

  const outgoing = groupOutgoing(graph.edges);

  if (type === "condition") {
    const nextEdge = edgeFor(outgoing, nodeId, "next");
    if (!nextEdge) return NO_CHANGE(graph);
    const target = nextEdge.target_node_id;
    const nodes = graph.nodes.map((item) =>
      item.node_id === nodeId
        ? {
            ...item,
            type: "condition" as AutomationNodeType,
            name: item.name === "New step" ? "Condition" : item.name,
            config: conditionConfig(),
          }
        : item
    );
    const edges = [
      ...graph.edges.map((edge) =>
        edge.edge_id === nextEdge.edge_id ? { ...edge, label: "true" } : edge
      ),
      makeEdge(graph, nodeId, target, "false"),
    ];
    return {
      graph: { ...graph, nodes, edges },
      persist: { kind: "structural" },
      focusNodeId: nodeId,
      removedNodeIds: [],
    };
  }

  const trueEdge = edgeFor(outgoing, nodeId, "true");
  if (!trueEdge) return NO_CHANGE(graph);
  const removed = new Set(conditionOnlyNodeIds(graph, nodeId));
  const nodes = graph.nodes
    .filter((item) => !removed.has(item.node_id))
    .map((item) =>
      item.node_id === nodeId
        ? {
            ...item,
            type: "action" as AutomationNodeType,
            name: item.name === "Condition" ? "New step" : item.name,
            config: {},
          }
        : item
    );
  const edges = graph.edges
    .filter((edge) => !removed.has(edge.source_node_id))
    .filter((edge) => !(edge.source_node_id === nodeId && edge.label === "false"))
    .map((edge) =>
      edge.edge_id === trueEdge.edge_id ? { ...edge, label: "next" } : edge
    );

  return {
    graph: { ...graph, nodes, edges: dedupeEdges(edges) },
    persist: { kind: "structural" },
    focusNodeId: nodeId,
    removedNodeIds: [...removed],
  };
}

/**
 * Point a branch straight at the final node: "nothing else runs on this path".
 *
 * There is no stop node type -- and the final node may not have outgoing edges --
 * so a stop is rendered from a lane edge whose target is the final node.
 */
export function stopLane(
  graph: AutomationGraphResponse,
  conditionNodeId: string,
  label: "true" | "false"
): GraphMutation {
  const outgoing = groupOutgoing(graph.edges);
  const laneEdge = edgeFor(outgoing, conditionNodeId, label);
  const finalNode = graph.nodes.find((item) => item.type === "final");
  if (!laneEdge || !finalNode || laneEdge.target_node_id === finalNode.node_id) {
    return NO_CHANGE(graph);
  }

  const otherLabel = label === "true" ? "false" : "true";
  const otherEdge = edgeFor(outgoing, conditionNodeId, otherLabel);
  const join =
    otherEdge
      ? findJoin(laneEdge.target_node_id, otherEdge.target_node_id, outgoing, topoOrder(graph)) ??
        finalNode.node_id
      : finalNode.node_id;
  const keep = otherEdge ? descendants(otherEdge.target_node_id, outgoing, join) : new Set<string>();
  const removed = new Set(
    [...descendants(laneEdge.target_node_id, outgoing, join)].filter(
      (id) => id !== join && !keep.has(id) && id !== finalNode.node_id
    )
  );

  const nodes = graph.nodes.filter((item) => !removed.has(item.node_id));
  const edges = graph.edges
    .filter((edge) => !removed.has(edge.source_node_id))
    .map((edge) =>
      edge.edge_id === laneEdge.edge_id ? { ...edge, target_node_id: finalNode.node_id } : edge
    );

  return {
    graph: { ...graph, nodes, edges: dedupeEdges(edges) },
    persist: { kind: "structural" },
    focusNodeId: conditionNodeId,
    removedNodeIds: [...removed],
  };
}

/**
 * Guarantee the boundary entities the backend requires.
 *
 * The API creates start, final, the connecting edge, and a manual trigger with
 * every automation, so this only repairs legacy or imported graphs. It never
 * touches positions, and reports whether anything actually changed so loading a
 * healthy graph does not mark it dirty.
 */
export function ensureChainSkeleton(
  graph: AutomationGraphResponse
): { graph: AutomationGraphResponse; changed: boolean } {
  let changed = false;
  let nodes = [...graph.nodes];
  let edges = [...graph.edges];

  let start = nodes.find((node) => node.type === "start");
  if (!start) {
    start = {
      node_id: createNodeId("start"),
      automation_id: graph.automation.automation_id,
      type: "start",
      name: "Start",
      alias: null,
      description: null,
      position: {},
      config: {},
      created_at: nowIso(),
      updated_at: null,
    };
    nodes = [start, ...nodes];
    changed = true;
  }

  let final = nodes.find((node) => node.type === "final");
  if (!final) {
    final = {
      node_id: createNodeId("final"),
      automation_id: graph.automation.automation_id,
      type: "final",
      name: "Done",
      alias: null,
      description: null,
      position: {},
      config: {},
      created_at: nowIso(),
      updated_at: null,
    };
    nodes = [...nodes, final];
    changed = true;
  }

  const nodeIds = new Set(nodes.map((node) => node.node_id));
  const validEdges = edges.filter(
    (edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id)
  );
  if (validEdges.length !== edges.length) {
    edges = validEdges;
    changed = true;
  }

  if (!edges.some((edge) => edge.source_node_id === start.node_id)) {
    edges = [...edges, makeEdge(graph, start.node_id, final.node_id, "next")];
    changed = true;
  }

  return { graph: { ...graph, nodes, edges }, changed };
}

/**
 * Layout hints for consumers that still read node positions.
 *
 * Chain order comes from edges, never from coordinates, but the marketplace and
 * any older reader expect an x/y, so derive a tidy one at save time.
 */
export function derivePositions(graph: AutomationGraphResponse): AutomationNode[] {
  const outgoing = groupOutgoing(graph.edges);
  const order = topoOrder(graph);
  const depth = new Map<string, number>();
  [...graph.nodes]
    .sort((left, right) => (order.get(left.node_id) ?? 0) - (order.get(right.node_id) ?? 0))
    .forEach((node) => {
      const current = depth.get(node.node_id) ?? 0;
      depth.set(node.node_id, current);
      (outgoing.get(node.node_id) ?? []).forEach((edge) => {
        depth.set(
          edge.target_node_id,
          Math.max(depth.get(edge.target_node_id) ?? 0, current + 1)
        );
      });
    });

  return graph.nodes.map((node) => ({
    ...node,
    position: { ...node.position, x: 0, y: (depth.get(node.node_id) ?? 0) * 140 },
  }));
}
