/**
 * Shared wiring for the recursively rendered chain.
 *
 * The column, lanes, and cards all need the same handful of things, so they read
 * them from context instead of threading a dozen props through every level.
 */

import { createContext, useContext } from "react";

import type {
  AutomationActionCatalogItem,
  AutomationGraphResponse,
  AutomationRunNodeResult,
} from "../../../../types/automation";
import type { ChainLaneLabel } from "../chain/chainModel";
import type { ChainStepType, NodePatch } from "../chain/chainOperations";
import type { ChainIssue } from "../chain/chainValidation";

export interface ChainContextValue {
  graph: AutomationGraphResponse;
  catalog: AutomationActionCatalogItem[];
  readOnly: boolean;
  expandedNodeId: string | null;
  issuesByNode: Map<string, ChainIssue[]>;
  /** Results of the selected run, keyed by node id. Empty when no run is selected. */
  resultsByNodeId: Map<string, AutomationRunNodeResult>;
  runContext: Record<string, unknown> | null;
  /** A run is executing right now, so results are still arriving. */
  runInProgress: boolean;
  onToggleExpand: (nodeId: string | null) => void;
  onOpenPalette: (edgeId: string) => void;
  onInsert: (edgeId: string, type: ChainStepType) => void;
  onPatchNode: (nodeId: string, patch: NodePatch) => void;
  onSetAction: (nodeId: string, item: AutomationActionCatalogItem) => void;
  onConfigureAction: (nodeId: string, item: AutomationActionCatalogItem) => void;
  onConvertType: (nodeId: string, type: ChainStepType) => void;
  onDeleteStep: (nodeId: string) => void;
  onMoveStep: (nodeId: string, direction: "up" | "down") => void;
  onStopLane: (conditionNodeId: string, label: ChainLaneLabel) => void;
  /** Reload the graph after a trigger changed, since triggers persist on their own. */
  onEditTriggers: () => Promise<void>;
}

export const ChainContext = createContext<ChainContextValue | null>(null);

export function useChain(): ChainContextValue {
  const value = useContext(ChainContext);
  if (!value) throw new Error("useChain must be used inside a ChainContext provider");
  return value;
}
