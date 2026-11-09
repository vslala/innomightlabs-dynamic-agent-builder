/**
 * The run as a whole: its status, timing and error, then the steps it ran in order. Selecting a step opens it
 * in the step panel.
 */

import { Loader2 } from "lucide-react";

import { Button } from "../../../../components/ui";
import type { AutomationRunResponse } from "../../../../types/automation";
import { RunStatusBadge } from "../components/RunStatusBadge";
import { formatDuration, formatRelativeTime, formatRunTime } from "../components/runStatus";
import { ExpandableText } from "./parts";
import { stepKind, stepName, type RunStep } from "./runSteps";

export function RunOverview({
  run,
  triggerType,
  steps,
  running,
  selectedStepId,
  onSelectStep,
}: {
  run: AutomationRunResponse;
  triggerType: string | null;
  steps: RunStep[];
  running: boolean;
  selectedStepId: string | null;
  onSelectStep: (resultId: string) => void;
}) {
  const duration = run.started_at ? formatDuration(run.started_at, run.completed_at) : null;
  const toolCalls = steps.reduce((total, step) => total + step.result.tool_call_count, 0);
  const succeeded = steps.filter((step) => step.result.status === "succeeded").length;

  return (
    <div className="run-inspector-overview">
      <section className="run-inspector-card run-inspector-summary" aria-label="Run summary">
        <div className="run-inspector-summary__head">
          <RunStatusBadge status={run.status} />
          <span title={formatRunTime(run.created_at)}>{formatRelativeTime(run.created_at)}</span>
        </div>
        {run.error ? (
          <div className="run-inspector-error" role="alert">
            <ExpandableText text={run.error} />
          </div>
        ) : null}
        <dl className="run-inspector-kpis">
          <Kpi label="Duration" value={duration ?? (running ? "Running" : "—")} />
          <Kpi label="Steps passed" value={`${succeeded}/${steps.length}`} />
          <Kpi label="Tool calls" value={String(toolCalls)} />
          <Kpi label="Trigger" value={triggerType ?? "—"} />
        </dl>
      </section>

      <nav className="run-inspector-card" aria-label="Steps in this run">
        <ol className="run-inspector-steps">
          {steps.map((step, index) => (
            <li key={step.result.result_id}>
              <Button
                type="button"
                variant="ghost"
                className="run-inspector-steps__row"
                aria-current={step.result.result_id === selectedStepId ? "true" : undefined}
                onClick={() => onSelectStep(step.result.result_id)}
              >
                <span className="run-inspector-steps__index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="run-inspector-steps__text">
                  <strong>{stepName(step)}</strong>
                  <small>
                    {stepKind(step)}
                    {step.result.tool_call_count > 0 ? ` · ${step.result.tool_call_count} tool calls` : ""}
                  </small>
                  <span className="run-inspector-steps__status">
                    <RunStatusBadge status={step.result.status} />
                    <small>{formatDuration(step.result.started_at, step.result.completed_at)}</small>
                  </span>
                </span>
              </Button>
            </li>
          ))}
          {running && (
            <li className="run-inspector-steps__running">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              <span>Running the next step. Its activity appears here when it finishes.</span>
            </li>
          )}
        </ol>
      </nav>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="run-inspector-kpis__item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
