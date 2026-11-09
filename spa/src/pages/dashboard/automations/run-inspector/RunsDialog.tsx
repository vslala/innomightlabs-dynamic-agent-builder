/**
 * Every run of the automation and the analytics over them, opened from the inspector to switch runs.
 * A bottom sheet on phones (the shared dialog does that below 640px).
 */

import { Link } from "react-router-dom";

import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../../../components/ui";
import { AutomationAnalyticsPanel } from "../components/AutomationAnalyticsPanel";
import { RunStatusBadge } from "../components/RunStatusBadge";
import { formatDuration, formatRelativeTime, formatRunTime } from "../components/runStatus";
import type { AutomationRunsState } from "../hooks/useAutomationRuns";

export function RunsDialog({
  open,
  onOpenChange,
  runs,
  currentRunId,
  runHref,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runs: AutomationRunsState;
  currentRunId: string;
  runHref: (runId: string) => string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="run-inspector-runs">
        <DialogHeader>
          <DialogTitle>Runs</DialogTitle>
          <DialogDescription>Pick a run to inspect, or see how this automation has been doing.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <Tabs defaultValue="runs">
            <TabsList>
              <TabsTrigger value="runs">Runs</TabsTrigger>
              <TabsTrigger value="analytics">Analytics</TabsTrigger>
            </TabsList>

            <TabsContent value="runs">
              {runs.runsError ? <div className="run-inspector-error">{runs.runsError}</div> : null}
              <ol className="run-inspector-run-list">
                {runs.runs.map((run) => (
                  <li key={run.run_id}>
                    <Link
                      to={runHref(run.run_id)}
                      className="run-inspector-run-list__row"
                      aria-current={run.run_id === currentRunId ? "page" : undefined}
                      onClick={() => onOpenChange(false)}
                    >
                      <RunStatusBadge status={run.status} />
                      <span className="run-inspector-run-list__text">
                        <strong>{formatRelativeTime(run.created_at)}</strong>
                        <small>{formatRunTime(run.created_at)}</small>
                        {run.error ? <small className="run-inspector-run-list__error">{run.error}</small> : null}
                      </span>
                      <span className="run-inspector-muted">
                        {run.started_at ? formatDuration(run.started_at, run.completed_at) : null}
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
              {runs.hasMore && (
                <Button variant="outline" className="run-inspector-wide" disabled={runs.loadingMore} onClick={() => void runs.loadMore()}>
                  {runs.loadingMore ? "Loading…" : "Load more"}
                </Button>
              )}
            </TabsContent>

            <TabsContent value="analytics">
              <AutomationAnalyticsPanel runs={runs.runs} />
            </TabsContent>
          </Tabs>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
