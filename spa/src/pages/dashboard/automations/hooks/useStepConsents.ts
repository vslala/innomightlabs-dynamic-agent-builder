/**
 * The owner's consent for steps that act for them, kept in step with the saved graph.
 *
 * A step is approved as it is saved (its fingerprint), so approving first waits for the pending autosave, then
 * approves what the server now holds. Editing a step makes its approval stale, and the card comes back.
 * See docs/LLD-action-consent.md.
 */

import { useCallback, useEffect, useState } from "react";

import { automationApiService } from "../../../../services/automations/AutomationApiService";
import type { AutomationGraphResponse } from "../../../../types/automation";
import type { StepConsentState } from "../../../../types/consent";
import type { SaveState } from "./useAutomationDraft";

export interface StepConsents {
  byNodeId: Map<string, StepConsentState>;
  approve: (nodeId: string, grantedActions?: string[]) => Promise<void>;
  revoke: (nodeId: string) => Promise<void>;
}

export function useStepConsents(
  graph: AutomationGraphResponse | null,
  saveState: SaveState,
  flush: () => Promise<boolean>
): StepConsents {
  const automationId = graph?.automation.automation_id;
  const [byNodeId, setByNodeId] = useState<Map<string, StepConsentState>>(new Map());

  const load = useCallback(async () => {
    if (!automationId) return new Map<string, StepConsentState>();
    const loaded = byNode(await automationApiService.listStepConsents(automationId));
    setByNodeId(loaded);
    return loaded;
  }, [automationId]);

  // Whenever what is saved changes: a step added or edited may now need approval, or its approval gone stale
  useEffect(() => {
    if (saveState !== "saved" || !automationId) return;
    let cancelled = false;
    automationApiService
      .listStepConsents(automationId)
      .then((states) => !cancelled && setByNodeId(byNode(states)))
      .catch((error) => console.error("Failed to load step approvals:", error));
    return () => {
      cancelled = true;
    };
  }, [graph, saveState, automationId]);

  const approve = useCallback(
    async (nodeId: string, grantedActions: string[] = []) => {
      if (!automationId) return;
      if (!(await flush())) throw new Error("Your changes haven't saved yet. Try again once they have.");
      const current = (await load()).get(nodeId);
      if (!current) return;
      const approved = await automationApiService.approveStep(automationId, nodeId, {
        fingerprint: current.fingerprint,
        granted_actions: grantedActions,
      });
      setByNodeId((states) => new Map(states).set(nodeId, approved));
    },
    [automationId, flush, load]
  );

  const revoke = useCallback(
    async (nodeId: string) => {
      if (!automationId) return;
      await automationApiService.revokeStep(automationId, nodeId);
      await load();
    },
    [automationId, load]
  );

  return { byNodeId, approve, revoke };
}

function byNode(states: StepConsentState[]): Map<string, StepConsentState> {
  return new Map(states.map((state) => [state.node_id, state]));
}
