/**
 * Optimistic graph state with debounced autosave.
 *
 * Two persistence paths, for two different kinds of edit:
 *  - field edits (name, reference name, description, config) coalesce per node
 *    and go out as PATCH /nodes/{id} after a short pause
 *  - structural edits (insert, delete, move, convert, stop a lane) touch several
 *    entities at once, so they flush immediately through PUT /graph, which the
 *    backend applies as one validated write
 *
 * Only one request is ever in flight. Local edits made while a request is
 * running win: the server response is adopted only when nothing changed
 * underneath it, so keystrokes are never rolled back.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { automationApiService } from "../../../../services/automations";
import type {
  AutomationActionCatalogItem,
  AutomationGraphResponse,
  AutomationNode,
} from "../../../../types/automation";
import { linearize, type Chain } from "../chain/chainModel";
import {
  derivePositions,
  ensureChainSkeleton,
  type GraphMutation,
  type NodePatch,
} from "../chain/chainOperations";
import { validateChain, type ChainIssue } from "../chain/chainValidation";

export type SaveState = "saved" | "saving" | "error";

const AUTOSAVE_DELAY_MS = 800;

export interface AutomationDraft {
  graph: AutomationGraphResponse | null;
  chain: Chain | null;
  catalog: AutomationActionCatalogItem[];
  issues: ChainIssue[];
  loading: boolean;
  loadError: string | null;
  saveState: SaveState;
  saveError: string | null;
  /** Apply a chain operation, then persist it the way the operation asks. */
  apply: (mutation: GraphMutation) => void;
  /** Convenience for field edits that should coalesce into one PATCH. */
  patchNode: (nodeId: string, patch: NodePatch) => void;
  /** Resolve once every queued save has completed. False when a save failed. */
  flush: () => Promise<boolean>;
  retry: () => void;
  reload: () => Promise<void>;
  /** Re-read the graph without a loading state, after a trigger write. */
  refreshGraph: () => Promise<void>;
  reloadCatalog: () => Promise<void>;
}

export function useAutomationDraft(automationId: string | undefined): AutomationDraft {
  const [graph, setGraph] = useState<AutomationGraphResponse | null>(null);
  const [catalog, setCatalog] = useState<AutomationActionCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);

  const graphRef = useRef<AutomationGraphResponse | null>(null);
  const revisionRef = useRef(0);
  const pendingPatches = useRef(new Map<string, NodePatch>());
  const pendingStructural = useRef(false);
  const runningRef = useRef(false);
  const timerRef = useRef<number | null>(null);
  const waitersRef = useRef<Array<(ok: boolean) => void>>([]);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const commitGraph = useCallback((next: AutomationGraphResponse) => {
    graphRef.current = next;
    revisionRef.current += 1;
    setGraph(next);
  }, []);

  const settleWaiters = useCallback((ok: boolean) => {
    const waiters = waitersRef.current;
    waitersRef.current = [];
    waiters.forEach((resolve) => resolve(ok));
  }, []);

  const hasPendingWork = () => pendingStructural.current || pendingPatches.current.size > 0;

  const runQueue = useCallback(async () => {
    if (runningRef.current || !automationId) return;
    const current = graphRef.current;
    if (!current || !hasPendingWork()) {
      // Nothing to send, so anything waiting on a flush can proceed.
      settleWaiters(true);
      return;
    }

    runningRef.current = true;
    setSaveState("saving");
    setSaveError(null);

    const revisionAtStart = revisionRef.current;
    const structural = pendingStructural.current;
    const patches = new Map(pendingPatches.current);
    pendingStructural.current = false;
    pendingPatches.current.clear();

    try {
      if (structural) {
        // Whole-graph writes must carry every node: the API treats an absent
        // node as deleted and runs its skill teardown hooks.
        const saved = await automationApiService.saveGraph(automationId, {
          nodes: derivePositions(current).map((node) => ({
            node_id: node.node_id,
            type: node.type,
            name: node.name,
            alias: node.alias ?? null,
            description: node.description ?? null,
            position: node.position,
            config: node.config,
          })),
          edges: current.edges.map((edge) => ({
            edge_id: edge.edge_id,
            source_node_id: edge.source_node_id,
            target_node_id: edge.target_node_id,
            label: edge.label,
            condition: edge.condition ?? null,
          })),
        });
        if (revisionRef.current === revisionAtStart) {
          graphRef.current = saved;
          setGraph(saved);
        }
      } else {
        const savedNodes: AutomationNode[] = [];
        for (const [nodeId, patch] of patches) {
          savedNodes.push(await automationApiService.updateNode(automationId, nodeId, patch));
        }
        if (revisionRef.current === revisionAtStart) {
          const byId = new Map(savedNodes.map((node) => [node.node_id, node]));
          const next = {
            ...current,
            nodes: current.nodes.map((node) => byId.get(node.node_id) ?? node),
          };
          graphRef.current = next;
          setGraph(next);
        }
      }

      runningRef.current = false;
      if (hasPendingWork()) {
        void runQueue();
      } else if (mountedRef.current) {
        setSaveState("saved");
        settleWaiters(true);
      }
    } catch (error) {
      // Keep the edits queued so the user can retry without retyping.
      if (structural) pendingStructural.current = true;
      patches.forEach((patch, nodeId) => {
        pendingPatches.current.set(nodeId, { ...patch, ...pendingPatches.current.get(nodeId) });
      });
      runningRef.current = false;
      if (mountedRef.current) {
        setSaveState("error");
        setSaveError(errorMessage(error));
      }
      settleWaiters(false);
    }
  }, [automationId, settleWaiters]);

  const scheduleQueue = useCallback(
    (immediate: boolean) => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      if (immediate) {
        void runQueue();
        return;
      }
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        void runQueue();
      }, AUTOSAVE_DELAY_MS);
    },
    [runQueue]
  );

  const apply = useCallback(
    (mutation: GraphMutation) => {
      if (mutation.persist.kind === "none") return;
      commitGraph(mutation.graph);

      if (mutation.persist.kind === "structural") {
        pendingStructural.current = true;
        // A structural write sends the whole graph, so it already carries any
        // field edits that were still waiting.
        pendingPatches.current.clear();
        setSaveState("saving");
        scheduleQueue(true);
        return;
      }

      const { nodeId, patch } = mutation.persist;
      pendingPatches.current.set(nodeId, { ...pendingPatches.current.get(nodeId), ...patch });
      setSaveState("saving");
      scheduleQueue(false);
    },
    [commitGraph, scheduleQueue]
  );

  const patchNode = useCallback(
    (nodeId: string, patch: NodePatch) => {
      const current = graphRef.current;
      if (!current) return;
      apply({
        graph: {
          ...current,
          nodes: current.nodes.map((node) =>
            node.node_id === nodeId ? { ...node, ...patch } : node
          ),
        },
        persist: { kind: "node", nodeId, patch },
        removedNodeIds: [],
      });
    },
    [apply]
  );

  const flush = useCallback(() => {
    if (!hasPendingWork() && !runningRef.current) return Promise.resolve(saveState !== "error");
    return new Promise<boolean>((resolve) => {
      waitersRef.current.push(resolve);
      scheduleQueue(true);
    });
  }, [saveState, scheduleQueue]);

  const retry = useCallback(() => scheduleQueue(true), [scheduleQueue]);

  const loadCatalog = useCallback(async () => {
    if (!automationId) return;
    const response = await automationApiService.getActionCatalog(automationId);
    if (mountedRef.current) setCatalog(response.actions);
  }, [automationId]);

  /**
   * Triggers persist through their own endpoints, so the workspace pulls the
   * graph again afterwards. Doing it without the loading flag keeps the expanded
   * card in place instead of replacing the page with a spinner.
   */
  const refreshGraph = useCallback(async () => {
    if (!automationId) return;
    try {
      const loaded = await automationApiService.getGraph(automationId);
      if (!mountedRef.current) return;
      graphRef.current = loaded;
      setGraph(loaded);
    } catch (error) {
      if (mountedRef.current) setSaveError(errorMessage(error));
    }
  }, [automationId]);

  const reload = useCallback(async () => {
    if (!automationId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const [loaded] = await Promise.all([automationApiService.getGraph(automationId), loadCatalog()]);
      const skeleton = ensureChainSkeleton(loaded);
      if (!mountedRef.current) return;
      graphRef.current = skeleton.graph;
      setGraph(skeleton.graph);
      if (skeleton.changed) {
        pendingStructural.current = true;
        scheduleQueue(true);
      }
    } catch (error) {
      if (mountedRef.current) setLoadError(errorMessage(error));
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [automationId, loadCatalog, scheduleQueue]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const chain = useMemo(() => (graph ? linearize(graph) : null), [graph]);
  const issues = useMemo(
    () => (graph && chain ? validateChain(graph, chain, catalog) : []),
    [catalog, chain, graph]
  );

  return {
    graph,
    chain,
    catalog,
    issues,
    loading,
    loadError,
    saveState,
    saveError,
    apply,
    patchNode,
    flush,
    retry,
    reload,
    refreshGraph,
    reloadCatalog: loadCatalog,
  };
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}
