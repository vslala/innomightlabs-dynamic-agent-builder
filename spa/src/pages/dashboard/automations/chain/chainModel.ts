/**
 * Linearizes the backend automation graph into the editor's rule chain.
 *
 * The backend stores a DAG (nodes plus labelled edges) and that stays the source
 * of truth. The editor renders a canonical shape of that DAG: a spine of steps
 * where each condition opens a `true` and a `false` lane that either rejoin at a
 * shared step or run straight to the final node.
 *
 * Any graph that cannot be expressed that way reports its nodes in
 * `Chain.unsupported` so the workspace can fall back to read-only instead of
 * silently dropping steps.
 */

import type {
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationTrigger,
} from "../../../../types/automation";

export type ChainLaneLabel = "true" | "false";

export interface TriggerChainItem {
  kind: "trigger";
  triggers: AutomationTrigger[];
  startNode: AutomationNode;
}

export interface StepChainItem {
  kind: "step";
  node: AutomationNode;
  /** Edge that leads into this item, used to anchor insert affordances. */
  incomingEdgeId: string | null;
}

export interface ConditionChainItem {
  kind: "condition";
  node: AutomationNode;
  incomingEdgeId: string | null;
  lanes: ChainLane[];
}

export interface EndChainItem {
  kind: "end";
  node: AutomationNode;
  incomingEdgeId: string | null;
}

export type ChainItem = TriggerChainItem | StepChainItem | ConditionChainItem | EndChainItem;

export interface ChainLane {
  label: ChainLaneLabel;
  /** Edge leaving the condition for this lane. Insert affordances anchor here. */
  edgeId: string | null;
  items: ChainItem[];
  /** The lane goes straight to the final node: nothing else runs on this branch. */
  stops: boolean;
  /** Edge that closes the lane, either into the join step or into the final node. */
  exitEdgeId: string | null;
}

export interface Chain {
  items: ChainItem[];
  startNode: AutomationNode | null;
  finalNode: AutomationNode | null;
  /** Nodes the linear editor cannot express. Non-empty means read-only. */
  unsupported: string[];
}

export function groupOutgoing(edges: AutomationEdge[]): Map<string, AutomationEdge[]> {
  const outgoing = new Map<string, AutomationEdge[]>();
  edges.forEach((edge) => {
    const list = outgoing.get(edge.source_node_id);
    if (list) list.push(edge);
    else outgoing.set(edge.source_node_id, [edge]);
  });
  return outgoing;
}

export function groupIncoming(edges: AutomationEdge[]): Map<string, AutomationEdge[]> {
  const incoming = new Map<string, AutomationEdge[]>();
  edges.forEach((edge) => {
    const list = incoming.get(edge.target_node_id);
    if (list) list.push(edge);
    else incoming.set(edge.target_node_id, [edge]);
  });
  return incoming;
}

export function edgeFor(
  outgoing: Map<string, AutomationEdge[]>,
  nodeId: string,
  label: string
): AutomationEdge | null {
  return outgoing.get(nodeId)?.find((edge) => edge.label === label) ?? null;
}

/** Kahn topological index per node. Order along any edge is strictly increasing. */
export function topoOrder(graph: AutomationGraphResponse): Map<string, number> {
  const indegree = new Map<string, number>();
  graph.nodes.forEach((node) => indegree.set(node.node_id, 0));
  graph.edges.forEach((edge) => {
    if (!indegree.has(edge.target_node_id)) return;
    indegree.set(edge.target_node_id, (indegree.get(edge.target_node_id) ?? 0) + 1);
  });

  const outgoing = groupOutgoing(graph.edges);
  const order = new Map<string, number>();
  const ready = graph.nodes.filter((node) => (indegree.get(node.node_id) ?? 0) === 0).map((node) => node.node_id);
  let index = 0;

  while (ready.length > 0) {
    const nodeId = ready.shift() as string;
    order.set(nodeId, index);
    index += 1;
    (outgoing.get(nodeId) ?? []).forEach((edge) => {
      const next = (indegree.get(edge.target_node_id) ?? 0) - 1;
      indegree.set(edge.target_node_id, next);
      if (next === 0) ready.push(edge.target_node_id);
    });
  }

  // Nodes left inside a cycle keep a stable index after everything ordered.
  graph.nodes.forEach((node) => {
    if (!order.has(node.node_id)) {
      order.set(node.node_id, index);
      index += 1;
    }
  });
  return order;
}

export function descendants(
  fromNodeId: string,
  outgoing: Map<string, AutomationEdge[]>,
  stopAt?: string | null
): Set<string> {
  const seen = new Set<string>();
  const stack = [fromNodeId];
  while (stack.length > 0) {
    const nodeId = stack.pop() as string;
    if (seen.has(nodeId)) continue;
    seen.add(nodeId);
    if (nodeId === stopAt) continue;
    (outgoing.get(nodeId) ?? []).forEach((edge) => stack.push(edge.target_node_id));
  }
  return seen;
}

export function ancestorNodeIds(graph: AutomationGraphResponse, nodeId: string): Set<string> {
  const incoming = groupIncoming(graph.edges);
  const seen = new Set<string>();
  const stack = [nodeId];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    (incoming.get(current) ?? []).forEach((edge) => {
      if (seen.has(edge.source_node_id)) return;
      seen.add(edge.source_node_id);
      stack.push(edge.source_node_id);
    });
  }
  return seen;
}

/** The earliest node both lanes reach: where the branch reconverges. */
export function findJoin(
  trueHead: string,
  falseHead: string,
  outgoing: Map<string, AutomationEdge[]>,
  order: Map<string, number>
): string | null {
  const fromTrue = descendants(trueHead, outgoing);
  const fromFalse = descendants(falseHead, outgoing);
  let join: string | null = null;
  fromTrue.forEach((nodeId) => {
    if (!fromFalse.has(nodeId)) return;
    if (join === null || (order.get(nodeId) ?? 0) < (order.get(join) ?? 0)) join = nodeId;
  });
  return join;
}

export function linearize(graph: AutomationGraphResponse): Chain {
  const nodeById = new Map(graph.nodes.map((node) => [node.node_id, node]));
  const startNodes = graph.nodes.filter((node) => node.type === "start");
  const finalNode = graph.nodes.find((node) => node.type === "final") ?? null;
  const startNode = startNodes[0] ?? null;

  if (!startNode || !finalNode || startNodes.length > 1) {
    return {
      items: startNode ? [{ kind: "trigger", triggers: graph.triggers, startNode }] : [],
      startNode,
      finalNode,
      unsupported: graph.nodes
        .filter((node) => node.type !== "start" && node.type !== "final")
        .map((node) => node.node_id),
    };
  }

  const final = finalNode;
  const outgoing = groupOutgoing(graph.edges);
  const order = topoOrder(graph);
  const unsupported = new Set<string>();
  const visited = new Set<string>();

  function walk(headNodeId: string | null, incomingEdgeId: string | null, stopAt: string | null): ChainItem[] {
    const items: ChainItem[] = [];
    let cursor = headNodeId;
    let entryEdgeId = incomingEdgeId;

    while (cursor && cursor !== stopAt) {
      const node = nodeById.get(cursor);
      if (!node) break;
      if (visited.has(cursor)) {
        unsupported.add(cursor);
        break;
      }
      visited.add(cursor);

      if (node.type === "final") {
        items.push({ kind: "end", node, incomingEdgeId: entryEdgeId });
        break;
      }

      const nodeEdges = outgoing.get(cursor) ?? [];

      if (node.type === "condition") {
        const trueEdge = edgeFor(outgoing, cursor, "true");
        const falseEdge = edgeFor(outgoing, cursor, "false");
        if (!trueEdge || !falseEdge || nodeEdges.length > 2) {
          unsupported.add(cursor);
          items.push({ kind: "condition", node, incomingEdgeId: entryEdgeId, lanes: [] });
          break;
        }
        const join = findJoin(trueEdge.target_node_id, falseEdge.target_node_id, outgoing, order);
        items.push({
          kind: "condition",
          node,
          incomingEdgeId: entryEdgeId,
          lanes: [
            buildLane("true", trueEdge, join),
            buildLane("false", falseEdge, join),
          ],
        });
        entryEdgeId = null;
        cursor = join && join !== cursor ? join : final.node_id;
        continue;
      }

      items.push({ kind: "step", node, incomingEdgeId: entryEdgeId });

      const nextEdge = edgeFor(outgoing, cursor, "next");
      if (!nextEdge || nodeEdges.length > 1) {
        unsupported.add(cursor);
        break;
      }
      entryEdgeId = nextEdge.edge_id;
      cursor = nextEdge.target_node_id;
    }

    return items;
  }

  function buildLane(label: ChainLaneLabel, edge: AutomationEdge, join: string | null): ChainLane {
    const stops = edge.target_node_id === final.node_id;
    const boundary = join ?? final.node_id;
    const items = stops ? [] : walk(edge.target_node_id, edge.edge_id, boundary);
    return {
      label,
      edgeId: edge.edge_id,
      items,
      stops,
      exitEdgeId: laneExitEdgeId(items, edge, outgoing),
    };
  }

  const entryEdge = edgeFor(outgoing, startNode.node_id, "next");
  const items: ChainItem[] = [{ kind: "trigger", triggers: graph.triggers, startNode }];
  visited.add(startNode.node_id);

  if (!entryEdge) {
    unsupported.add(startNode.node_id);
  } else {
    items.push(...walk(entryEdge.target_node_id, entryEdge.edge_id, null));
  }

  graph.nodes.forEach((node) => {
    if (node.type === "start" || node.type === "final") return;
    if (!visited.has(node.node_id)) unsupported.add(node.node_id);
  });

  return { items, startNode, finalNode, unsupported: [...unsupported] };
}

function laneExitEdgeId(
  items: ChainItem[],
  laneEdge: AutomationEdge,
  outgoing: Map<string, AutomationEdge[]>
): string | null {
  const last = items[items.length - 1];
  if (!last) return laneEdge.edge_id;
  if (last.kind === "step") return edgeFor(outgoing, last.node.node_id, "next")?.edge_id ?? null;
  return null;
}

/** Editable steps in reading order, flattening branch lanes depth-first. */
export function flattenSteps(chain: Chain): AutomationNode[] {
  const steps: AutomationNode[] = [];
  const visit = (items: ChainItem[]) => {
    items.forEach((item) => {
      if (item.kind === "step") steps.push(item.node);
      if (item.kind === "condition") {
        steps.push(item.node);
        item.lanes.forEach((lane) => visit(lane.items));
      }
    });
  };
  visit(chain.items);
  return steps;
}

export function findChainItem(chain: Chain, nodeId: string): ChainItem | null {
  let found: ChainItem | null = null;
  const visit = (items: ChainItem[]) => {
    items.forEach((item) => {
      if (found) return;
      if (item.kind !== "trigger" && item.node.node_id === nodeId) {
        found = item;
        return;
      }
      if (item.kind === "condition") item.lanes.forEach((lane) => visit(lane.items));
    });
  };
  visit(chain.items);
  return found;
}

/** Edge that the trailing "Add step" button should insert on. */
export function tailEdgeId(chain: Chain): string | null {
  for (let index = chain.items.length - 1; index >= 0; index -= 1) {
    const item = chain.items[index];
    if (item.kind === "end") return item.incomingEdgeId;
  }
  return null;
}

export function isChainEditable(chain: Chain): boolean {
  return chain.unsupported.length === 0 && chain.startNode !== null && chain.finalNode !== null;
}
