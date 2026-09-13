/**
 * Run history, docked to the bottom of the workspace.
 *
 * Selecting a run puts the whole chain into run view: each step card shows that
 * run's status, input, and output. Run history used to be a separate route,
 * which is what forced users to leave the builder to see what happened.
 */

import { ChevronDown, ChevronUp, History, Loader2 } from "lucide-react";

import { Button, Tabs, TabsContent, TabsList, TabsTrigger } from "../../../../components/ui";
import type { AutomationRunResponse } from "../../../../types/automation";
import type { AutomationRunsState } from "../hooks/useAutomationRuns";
import { AutomationAnalyticsPanel } from "./AutomationAnalyticsPanel";
import { RunStatusBadge } from "./RunStatusBadge";
import { formatRelativeTime, formatRunTime } from "./runStatus";

export type DrawerHeight = "rail" | "half";

export function RunsDrawer({
  runs,
  onSelectRun,
  height,
  tab,
  onHeightChange,
  onTabChange,
}: {
  runs: AutomationRunsState;
  /** Selection is owned by the `run` query parameter, not by this component. */
  onSelectRun: (runId: string | null) => void;
  height: DrawerHeight;
  tab: "runs" | "analytics";
  onHeightChange: (height: DrawerHeight) => void;
  onTabChange: (tab: "runs" | "analytics") => void;
}) {
  const expanded = height === "half";

  return (
    <aside className={`automation-drawer automation-drawer--${height}`}>
      <div className="automation-drawer__handle">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => onHeightChange(expanded ? "rail" : "half")}
          aria-expanded={expanded}
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          <History className="h-4 w-4" />
          Runs
        </Button>

        {!expanded && (
          <div className="automation-drawer__rail">
            {runs.loadingRuns && runs.runs.length === 0 ? (
              <span className="automation-drawer__hint">Loading run history…</span>
            ) : runs.runs.length === 0 ? (
              <span className="automation-drawer__hint">No runs yet. Use Test to try it.</span>
            ) : (
              runs.runs.slice(0, 6).map((run) => (
                <RunChip
                  key={run.run_id}
                  run={run}
                  selected={runs.selectedRunId === run.run_id}
                  onSelect={() => onSelectRun(run.run_id)}
                />
              ))
            )}
          </div>
        )}

        {runs.isRunning && (
          <span className="automation-drawer__running">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Running
          </span>
        )}
      </div>

      {expanded && (
        <div className="automation-drawer__body">
          <Tabs value={tab} onValueChange={(value) => onTabChange(value as "runs" | "analytics")}>
            <TabsList>
              <TabsTrigger value="runs">Runs</TabsTrigger>
              <TabsTrigger value="analytics">Analytics</TabsTrigger>
            </TabsList>

            <TabsContent value="runs">
              {runs.runsError ? <div className="automation-drawer__error">{runs.runsError}</div> : null}
              <div className="automation-drawer__list">
                {runs.runs.length === 0 ? (
                  <p className="automation-drawer__hint">
                    No runs yet. Press Test to run this automation once.
                  </p>
                ) : (
                  runs.runs.map((run) => (
                    <Button
                      key={run.run_id}
                      type="button"
                      variant="ghost"
                      className={
                        runs.selectedRunId === run.run_id
                          ? "automation-drawer__row automation-drawer__row--selected"
                          : "automation-drawer__row"
                      }
                      onClick={() => onSelectRun(run.run_id)}
                    >
                      <RunStatusBadge status={run.status} />
                      <span className="automation-drawer__row-text">
                        <strong>{formatRelativeTime(run.created_at)}</strong>
                        <small>{formatRunTime(run.created_at)}</small>
                      </span>
                      {run.error ? <span className="automation-drawer__row-error">{run.error}</span> : null}
                    </Button>
                  ))
                )}
                {runs.hasMore && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={runs.loadingMore}
                    onClick={() => void runs.loadMore()}
                  >
                    {runs.loadingMore ? "Loading…" : "Load more"}
                  </Button>
                )}
              </div>

              {runs.selectedRunId && (
                <p className="automation-drawer__hint">
                  Showing this run on the steps above. Expand any step to see what it received and
                  returned.{" "}
                  <Button variant="ghost" size="sm" onClick={() => onSelectRun(null)}>
                    Clear
                  </Button>
                </p>
              )}
            </TabsContent>

            <TabsContent value="analytics">
              <AutomationAnalyticsPanel runs={runs.runs} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </aside>
  );
}

function RunChip({
  run,
  selected,
  onSelect,
}: {
  run: AutomationRunResponse;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={selected ? "automation-drawer__chip automation-drawer__chip--selected" : "automation-drawer__chip"}
      onClick={onSelect}
      title={formatRunTime(run.created_at)}
    >
      <RunStatusBadge status={run.status} label={formatRelativeTime(run.created_at)} />
    </Button>
  );
}
