/**
 * `/dashboard/automations/:automationId/runs/:runId`: everything one run did, step by step and tool call by tool
 * call, laid out for a phone first.
 *
 * The step, tab and tool call open live in the query string (`?step=<result id>&tab=&call=<tool call id>`), so a
 * link can point at one exact move of the agent. A run still executing is followed until it finishes.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ChevronLeft, History } from "lucide-react";

import { Button, LinkButton, Spinner } from "../../../../components/ui";
import { automationApiService } from "../../../../services/automations";
import type { AutomationNode } from "../../../../types/automation";
import { useAutomationRuns } from "../hooks/useAutomationRuns";
import { useWorkspaceParams } from "../hooks/useWorkspaceParams";
import { useAutomationDetailContext } from "../types";
import { RunOverview } from "./RunOverview";
import { RunStepPanel } from "./RunStepPanel";
import { RunsDialog } from "./RunsDialog";
import { defaultTab, firstStepToInspect, hasActivity, isInspectorTab, runSteps, type InspectorTab } from "./runSteps";
import "./run-inspector.css";

export function RunInspectorPage() {
  const { automationId = "", runId = "" } = useParams<{ automationId: string; runId: string }>();
  const { automation } = useAutomationDetailContext();
  const params = useWorkspaceParams();
  const runs = useAutomationRuns(automationId);
  const nodes = useGraphNodes(automationId);
  const [runsOpen, setRunsOpen] = useState(false);

  const { selectRun, selectedRunId } = runs;
  useEffect(() => {
    if (selectedRunId !== runId) selectRun(runId);
  }, [runId, selectRun, selectedRunId]);

  const detail = runs.detail?.run.run_id === runId ? runs.detail : null;
  const steps = useMemo(() => (detail ? runSteps(detail.node_results, nodes) : []), [detail, nodes]);
  const step = steps.find((item) => item.result.result_id === params.step) ?? firstStepToInspect(steps);
  const tab: InspectorTab | null = step
    ? isInspectorTab(params.tab) && (params.tab !== "activity" || hasActivity(step))
      ? params.tab
      : defaultTab(step)
    : null;

  const runHref = (id: string) => `/dashboard/automations/${automationId}/runs/${id}`;
  const builderHref = `/dashboard/automations/${automationId}?run=${runId}&panel=runs`;
  const triggerType = detail ? triggerTypeOf(detail.context) : null;

  return (
    <div className="run-inspector">
      <header className="run-inspector__bar">
        <LinkButton to={builderHref} variant="ghost" size="icon" aria-label="Back to the builder">
          <ChevronLeft className="h-5 w-5" />
        </LinkButton>
        <div className="run-inspector__title">
          <small>Run inspector</small>
          <h1>{automation.title}</h1>
        </div>
        <Button variant="outline" size="sm" onClick={() => setRunsOpen(true)}>
          <History className="h-4 w-4" />
          Runs
        </Button>
      </header>

      {!detail ? (
        <div className="run-inspector-empty" role={runs.runsError ? "alert" : "status"}>
          {runs.runsError ? <span>{runs.runsError}</span> : <><Spinner size="sm" /><span>Loading the run…</span></>}
        </div>
      ) : (
        <main className="run-inspector__layout">
          <RunOverview
            run={detail.run}
            triggerType={triggerType}
            steps={steps}
            running={runs.isRunning}
            selectedStepId={step?.result.result_id ?? null}
            onSelectStep={(resultId) => params.update({ step: resultId, tab: null, call: null })}
          />
          {step && tab ? (
            <RunStepPanel
              key={step.result.result_id}
              automationId={automationId}
              step={step}
              tab={tab}
              selectedCallId={params.call}
              onTabChange={(next) => params.update({ tab: next })}
              onSelectCall={(callId) => params.update({ call: callId })}
            />
          ) : (
            <div className="run-inspector-card run-inspector-empty">
              <span>{runs.isRunning ? "Waiting for the first step to finish…" : "This run recorded no steps."}</span>
            </div>
          )}
        </main>
      )}

      <RunsDialog open={runsOpen} onOpenChange={setRunsOpen} runs={runs} currentRunId={runId} runHref={runHref} />
    </div>
  );
}

/** The graph's nodes, for step names: a result records only the node id. */
function useGraphNodes(automationId: string): AutomationNode[] {
  const [nodes, setNodes] = useState<AutomationNode[]>([]);
  useEffect(() => {
    let current = true;
    automationApiService
      .getGraph(automationId)
      .then((graph) => current && setNodes(graph.nodes))
      // Without the graph the steps still show, under their ids
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [automationId]);
  return nodes;
}

function triggerTypeOf(context: Record<string, unknown>): string | null {
  const trigger = context.trigger;
  if (typeof trigger !== "object" || trigger === null) return null;
  const type = (trigger as Record<string, unknown>).type;
  return typeof type === "string" ? type.replace(/_/g, " ") : null;
}
