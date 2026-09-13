/**
 * The automation workspace: one screen for building, testing, and inspecting.
 *
 * Replaces the canvas builder plus the separate triggers, runs, and analytics
 * routes. Panel state lives in the query string (`?step=`, `?panel=`, `?run=`)
 * so everything stays deep-linkable.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Plus } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import "./styles.css";
import "./workspace.css";

import {
  Button,
  ConfirmationDialog,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  ErrorState,
  LoadingState,
} from "../../../components/ui";
import { SchemaForm } from "../../../components/forms";
import { automationApiService } from "../../../services/automations";
import type {
  AutomationActionCatalogItem,
  AutomationStatus,
} from "../../../types/automation";
import type { FormValue } from "../../../types/form";
import { tailEdgeId } from "./chain/chainModel";
import {
  convertStepType,
  deleteStep,
  insertStepOnEdge,
  moveStep,
  setStepAction,
  stopLane,
  type ChainStepType,
} from "./chain/chainOperations";
import { errorCount, issuesByNode } from "./chain/chainValidation";
import { AddStepPalette, type PaletteChoice } from "./components/AddStepPalette";
import { ChainColumn } from "./components/ChainColumn";
import { ChainContext, type ChainContextValue } from "./components/chainContext";
import { IssuesPanel } from "./components/IssuesPanel";
import { RunsDrawer, type DrawerHeight } from "./components/RunsDrawer";
import { TestPanel } from "./components/TestPanel";
import { WorkspaceTopBar } from "./components/WorkspaceTopBar";
import { useAutomationDraft } from "./hooks/useAutomationDraft";
import { useAutomationRuns } from "./hooks/useAutomationRuns";
import { useWorkspaceParams } from "./hooks/useWorkspaceParams";
import { useAutomationDetailContext } from "./types";

interface PendingDelete {
  nodeId: string;
  removedCount: number;
}

export function AutomationWorkspacePage() {
  const { automationId } = useParams<{ automationId: string }>();
  const navigate = useNavigate();
  const { automation, reloadAutomation, openPublishDialog } = useAutomationDetailContext();
  const params = useWorkspaceParams();

  const draft = useAutomationDraft(automationId);
  const runs = useAutomationRuns(automationId);

  const [paletteEdgeId, setPaletteEdgeId] = useState<string | null>(null);
  const [paletteLane, setPaletteLane] = useState<string | null>(null);
  const [setupFor, setSetupFor] = useState<{ nodeId: string; item: AutomationActionCatalogItem } | null>(
    null
  );
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [confirmDeleteAutomation, setConfirmDeleteAutomation] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [drawerHeight, setDrawerHeight] = useState<DrawerHeight>("rail");
  const [testOpen, setTestOpen] = useState(false);

  const { step: expandedNodeId, panel, run: runParam, focus, update } = params;
  const issuesOpen = panel === "issues";
  const drawerTab = panel === "analytics" ? "analytics" : "runs";

  // Deep links open the drawer at the right place.
  useEffect(() => {
    if (panel === "runs" || panel === "analytics") setDrawerHeight("half");
  }, [panel]);

  /*
   * The URL is the only source of truth for the selected run: the drawer writes
   * `?run=`, and this effect is the single place that tells the runs hook about
   * it. Syncing in both directions is what previously let a click and the URL
   * fight each other.
   */
  const { selectRun, selectedRunId } = runs;
  useEffect(() => {
    if (runParam !== selectedRunId) selectRun(runParam);
  }, [runParam, selectRun, selectedRunId]);

  const selectRunFromDrawer = useCallback(
    (runId: string | null) => {
      update({ run: runId, panel: runId ? "runs" : null });
      if (runId) setDrawerHeight("half");
    },
    [update]
  );

  const toggleExpand = useCallback((nodeId: string | null) => update({ step: nodeId }), [update]);

  // `?focus=trigger` arrives from the retired /triggers route. Both keys move in
  // one navigation, so neither write can discard the other.
  useEffect(() => {
    const startNodeId = draft.chain?.startNode?.node_id;
    if (focus !== "trigger" || !startNodeId) return;
    update({ step: startNodeId, focus: null });
  }, [draft.chain?.startNode?.node_id, focus, update]);

  const insert = useCallback(
    (edgeId: string, type: ChainStepType) => {
      if (!draft.graph) return;
      const mutation = insertStepOnEdge(draft.graph, edgeId, type);
      draft.apply(mutation);
      if (mutation.focusNodeId) toggleExpand(mutation.focusNodeId);
      return mutation.focusNodeId ?? null;
    },
    [draft, toggleExpand]
  );

  const handlePaletteChoice = useCallback(
    (choice: PaletteChoice) => {
      if (!draft.graph || !paletteEdgeId) return;
      const edgeId = paletteEdgeId;
      setPaletteEdgeId(null);

      if (choice.kind === "condition") {
        insert(edgeId, "condition");
        return;
      }

      if (choice.kind === "stop") {
        const edge = draft.graph.edges.find((item) => item.edge_id === edgeId);
        if (!edge || (edge.label !== "true" && edge.label !== "false")) return;
        draft.apply(stopLane(draft.graph, edge.source_node_id, edge.label));
        return;
      }

      const inserted = insertStepOnEdge(draft.graph, edgeId, "action");
      if (!inserted.focusNodeId) return;
      const withAction = setStepAction(inserted.graph, inserted.focusNodeId, choice.item);
      // One structural write carries both the new step and its action.
      draft.apply({
        graph: withAction.graph,
        persist: { kind: "structural" },
        removedNodeIds: [],
        focusNodeId: inserted.focusNodeId,
      });
      toggleExpand(inserted.focusNodeId);
      if (!choice.item.available && choice.item.install_schema) {
        setSetupFor({ nodeId: inserted.focusNodeId, item: choice.item });
      }
    },
    [draft, insert, paletteEdgeId, toggleExpand]
  );

  const requestDelete = useCallback(
    (nodeId: string) => {
      if (!draft.graph) return;
      const mutation = deleteStep(draft.graph, nodeId);
      if (mutation.persist.kind === "none") return;
      if (mutation.removedNodeIds.length > 1) {
        setPendingDelete({ nodeId, removedCount: mutation.removedNodeIds.length });
        return;
      }
      draft.apply(mutation);
      if (expandedNodeId === nodeId) toggleExpand(null);
    },
    [draft, expandedNodeId, toggleExpand]
  );

  const confirmDelete = useCallback(() => {
    if (!draft.graph || !pendingDelete) return;
    draft.apply(deleteStep(draft.graph, pendingDelete.nodeId));
    if (expandedNodeId === pendingDelete.nodeId) toggleExpand(null);
    setPendingDelete(null);
  }, [draft, expandedNodeId, pendingDelete, toggleExpand]);

  const submitSetup = useCallback(
    async (values: Record<string, FormValue>) => {
      if (!automationId || !setupFor) return;
      setSetupBusy(true);
      setSetupError(null);
      try {
        const installed = await automationApiService.enableSkill(automationId, setupFor.item.skill_id, {
          config: Object.fromEntries(
            Object.entries(values).map(([key, value]) => [key, typeof value === "string" ? value : value ?? ""])
          ),
        });
        await draft.reloadCatalog();
        draft.patchNode(setupFor.nodeId, {
          config: {
            action_type: "skill_action",
            installed_skill_id: installed.installed_skill_id,
            skill_id: installed.skill_id,
            action: setupFor.item.action,
            arguments: {},
          },
        });
        setSetupFor(null);
      } catch (error) {
        setSetupError(error instanceof Error ? error.message : "Could not configure this action.");
      } finally {
        setSetupBusy(false);
      }
    },
    [automationId, draft, setupFor]
  );

  const changeStatus = useCallback(
    async (status: AutomationStatus) => {
      if (!automationId) return;
      setStatusBusy(true);
      setServerError(null);
      try {
        await draft.flush();
        await automationApiService.updateAutomation(automationId, { status });
        await reloadAutomation();
      } catch (error) {
        setServerError(error instanceof Error ? error.message : "Could not change the status.");
        update({ panel: "issues" });
      } finally {
        setStatusBusy(false);
      }
    },
    [automationId, draft, reloadAutomation, update]
  );

  const rename = useCallback(
    async (title: string) => {
      if (!automationId) return;
      try {
        await automationApiService.updateAutomation(automationId, { title });
        await reloadAutomation();
      } catch (error) {
        setServerError(error instanceof Error ? error.message : "Could not rename the automation.");
      }
    },
    [automationId, reloadAutomation]
  );

  const removeAutomation = useCallback(async () => {
    if (!automationId) return;
    try {
      await automationApiService.deleteAutomation(automationId);
      navigate("/dashboard/automations");
    } catch (error) {
      setServerError(error instanceof Error ? error.message : "Could not delete the automation.");
    }
  }, [automationId, navigate]);

  const runTest = useCallback(
    async (input: Record<string, unknown>) => {
      setServerError(null);
      const saved = await draft.flush();
      if (!saved) {
        setServerError("Your latest change has not been saved yet. Retry the save and run again.");
        return;
      }
      const run = await runs.startTestRun(input);
      if (run) {
        setTestOpen(false);
        setDrawerHeight("half");
        // Selection goes through the URL like every other run selection.
        update({ run: run.run_id, panel: "runs" });
      }
    },
    [draft, runs, update]
  );

  const chainValue = useMemo<ChainContextValue | null>(() => {
    if (!draft.graph || !draft.chain) return null;
    return {
      graph: draft.graph,
      catalog: draft.catalog,
      readOnly: draft.chain.unsupported.length > 0,
      expandedNodeId,
      issuesByNode: issuesByNode(draft.issues),
      resultsByNodeId: runs.resultsByNodeId,
      runContext: runs.context,
      runInProgress: runs.isRunning,
      onToggleExpand: toggleExpand,
      onOpenPalette: (edgeId) => {
        const edge = draft.graph?.edges.find((item) => item.edge_id === edgeId);
        setPaletteLane(edge && (edge.label === "true" || edge.label === "false") ? edge.label : null);
        setPaletteEdgeId(edgeId);
      },
      onInsert: insert,
      onPatchNode: draft.patchNode,
      onSetAction: (nodeId, item) => {
        if (!draft.graph) return;
        draft.apply(setStepAction(draft.graph, nodeId, item));
      },
      onConfigureAction: (nodeId, item) => setSetupFor({ nodeId, item }),
      onConvertType: (nodeId, type) => {
        if (!draft.graph) return;
        draft.apply(convertStepType(draft.graph, nodeId, type));
      },
      onDeleteStep: requestDelete,
      onMoveStep: (nodeId, direction) => {
        if (!draft.graph) return;
        draft.apply(moveStep(draft.graph, nodeId, direction));
      },
      onStopLane: (conditionNodeId, label) => {
        if (!draft.graph) return;
        draft.apply(stopLane(draft.graph, conditionNodeId, label));
      },
      onEditTriggers: draft.refreshGraph,
    };
  }, [draft, expandedNodeId, insert, requestDelete, runs, toggleExpand]);

  if (draft.loading) return <LoadingState />;
  if (draft.loadError || !draft.graph || !draft.chain || !chainValue) {
    return <ErrorState message={draft.loadError ?? "Could not load this automation."} onRetry={draft.reload} />;
  }

  const tailEdge = tailEdgeId(draft.chain);
  const readOnly = chainValue.readOnly;

  return (
    <div className="automation-workspace">
      <WorkspaceTopBar
        automation={automation}
        saveState={draft.saveState}
        saveError={draft.saveError}
        errorCount={errorCount(draft.issues)}
        onRetrySave={draft.retry}
        onRename={(title) => void rename(title)}
        onStatusChange={(status) => void changeStatus(status)}
        onTest={() => setTestOpen(true)}
        onPublish={openPublishDialog}
        onDelete={() => setConfirmDeleteAutomation(true)}
        onShowIssues={() => update({ panel: issuesOpen ? null : "issues" })}
        busy={statusBusy}
      />

      {readOnly && (
        <div className="automation-workspace__banner">
          <AlertTriangle className="h-4 w-4" />
          <div>
            <strong>This workflow uses a shape the step editor cannot show</strong>
            <p>
              It branches or connects in a way the linear editor does not express, so it is shown
              read-only to avoid changing what it does. Steps and connections are intact and it
              still runs.
            </p>
          </div>
        </div>
      )}

      <div className="automation-workspace__main">
        <div className="automation-workspace__chain">
          <ChainContext.Provider value={chainValue}>
            <ChainColumn items={draft.chain.items} />
          </ChainContext.Provider>

          {!readOnly && (
            <Button
              variant="outline"
              className="automation-workspace__add"
              onClick={() => tailEdge && setPaletteEdgeId(tailEdge)}
              disabled={!tailEdge}
            >
              <Plus className="h-4 w-4" />
              Add a step
            </Button>
          )}
        </div>

        {issuesOpen && (
          <IssuesPanel
            issues={draft.issues}
            serverError={serverError}
            graph={draft.graph}
            onClose={() => update({ panel: null })}
            onSelectStep={(nodeId) => toggleExpand(nodeId)}
          />
        )}

        <TestPanel
          graph={draft.graph}
          open={testOpen}
          running={runs.isRunning}
          error={runs.startError ?? serverError}
          onClose={() => setTestOpen(false)}
          onRun={(input) => void runTest(input)}
        />
      </div>

      <RunsDrawer
        runs={runs}
        onSelectRun={selectRunFromDrawer}
        height={drawerHeight}
        tab={drawerTab}
        onHeightChange={setDrawerHeight}
        onTabChange={(tab) => update({ panel: tab })}
      />

      <AddStepPalette
        key={paletteEdgeId ?? "closed"}
        open={paletteEdgeId !== null}
        catalog={draft.catalog}
        allowStop={paletteLane !== null}
        onClose={() => setPaletteEdgeId(null)}
        onChoose={handlePaletteChoice}
      />

      {setupFor?.item.install_schema && (
        <Dialog open onOpenChange={(next) => (next ? undefined : setSetupFor(null))}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Configure {setupFor.item.label}</DialogTitle>
              <DialogDescription>
                {setupFor.item.disabled_reason ?? "This action needs a few details before it can run."}
              </DialogDescription>
            </DialogHeader>
            <DialogBody>
              {setupError ? <div className="automation-workspace__error">{setupError}</div> : null}
              <SchemaForm
                schema={setupFor.item.install_schema}
                submitLabel="Save and use"
                cancelLabel="Cancel"
                isLoading={setupBusy}
                onCancel={() => setSetupFor(null)}
                onSubmit={submitSetup}
              />
            </DialogBody>
          </DialogContent>
        </Dialog>
      )}

      <ConfirmationDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => (open ? undefined : setPendingDelete(null))}
        title="Delete this condition?"
        description={`This also removes ${(pendingDelete?.removedCount ?? 1) - 1} step${
          (pendingDelete?.removedCount ?? 2) - 1 === 1 ? "" : "s"
        } that only the other branch could reach.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={confirmDelete}
      />

      <ConfirmationDialog
        open={confirmDeleteAutomation}
        onOpenChange={setConfirmDeleteAutomation}
        title="Delete this automation?"
        description="The workflow, its triggers, and its run history stop being available. This cannot be undone."
        confirmText="Delete"
        variant="destructive"
        onConfirm={() => void removeAutomation()}
      />
    </div>
  );
}
