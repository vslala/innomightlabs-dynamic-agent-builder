/**
 * Summary of the runs already loaded in the drawer.
 *
 * Deliberately derived from the loaded page of runs rather than a new endpoint,
 * so the tab says something true without inventing an aggregate the API does
 * not provide yet.
 */

import type { AutomationRunResponse } from "../../../../types/automation";
import { formatRelativeTime } from "./runStatus";

export function AutomationAnalyticsPanel({ runs }: { runs: AutomationRunResponse[] }) {
  if (runs.length === 0) {
    return (
      <p className="automation-drawer__hint">
        Analytics appear once this automation has run at least once.
      </p>
    );
  }

  const succeeded = runs.filter((run) => run.status === "succeeded").length;
  const failed = runs.filter((run) => run.status === "failed").length;
  const running = runs.filter((run) => run.status === "running" || run.status === "pending").length;
  const finished = succeeded + failed;
  const successRate = finished > 0 ? Math.round((succeeded / finished) * 100) : null;
  const durations = runs
    .map((run) => durationMs(run))
    .filter((value): value is number => value !== null);
  const median = durations.length > 0 ? medianOf(durations) : null;

  return (
    <div className="automation-analytics">
      <dl className="automation-analytics__stats">
        <Stat label={`Runs (last ${runs.length})`} value={String(runs.length)} />
        <Stat label="Succeeded" value={String(succeeded)} />
        <Stat label="Failed" value={String(failed)} />
        {running > 0 ? <Stat label="In progress" value={String(running)} /> : null}
        <Stat label="Success rate" value={successRate === null ? "—" : `${successRate}%`} />
        <Stat label="Median duration" value={median === null ? "—" : formatMs(median)} />
        <Stat label="Last run" value={formatRelativeTime(runs[0].created_at)} />
      </dl>
      <p className="automation-drawer__hint">
        Based on the runs loaded here. Load more in the Runs tab to widen the window.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="automation-analytics__stat">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function durationMs(run: AutomationRunResponse): number | null {
  if (!run.started_at || !run.completed_at) return null;
  const ms = new Date(run.completed_at).getTime() - new Date(run.started_at).getTime();
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}

function medianOf(values: number[]): number {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}
