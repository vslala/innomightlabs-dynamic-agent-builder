import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import "./styles.css";

import {
  Button,
  Card,
  CardContent,
  ErrorState,
  LoadingState,
  StatusBadge,
  type StatusBadgeProps,
} from "../../../components/ui";
import { automationApiService } from "../../../services/automations";
import type {
  AutomationNodeRunStatus,
  AutomationRunDetailResponse,
  AutomationRunResponse,
  AutomationRunStatus,
  PaginatedResponse,
} from "../../../types/automation";
import { AutomationJsonTreeViewer } from "./components/AutomationJsonEditor";
import { filterRuntimeLogContext, getRuntimeLogSteps, type RuntimeLogStep } from "./runDisplay";
import { useAutomationDetailContext } from "./types";

type RunBadgeStatus = StatusBadgeProps["status"];

function runBadgeStatus(status: AutomationRunStatus | AutomationNodeRunStatus): RunBadgeStatus {
  if (status === "succeeded") return "success";
  if (status === "running") return "in_progress";
  if (status === "skipped") return "inactive";
  return status;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function AutomationRunsPage() {
  const { automation } = useAutomationDetailContext();
  const [runs, setRuns] = useState<AutomationRunResponse[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [selectedRun, setSelectedRun] = useState<AutomationRunDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedRuntimeSteps, setExpandedRuntimeSteps] = useState<Set<string>>(new Set());

  const loadRuns = useCallback(async (cursor?: string | null) => {
    const isLoadMore = Boolean(cursor);
    if (isLoadMore) {
      setLoadingMore(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const page: PaginatedResponse<AutomationRunResponse> = await automationApiService.listRuns(
        automation.automation_id,
        20,
        cursor
      );
      setRuns((current) => (isLoadMore ? [...current, ...page.items] : page.items));
      setNextCursor(page.next_cursor ?? null);
      setHasMore(page.has_more);
    } catch (err) {
      console.error("Error loading automation runs:", err);
      setError("Failed to load automation runs. Please try again.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [automation.automation_id]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const openRun = async (runId: string) => {
    try {
      const detail = await automationApiService.getRun(automation.automation_id, runId);
      setSelectedRun(detail);
      const firstStepWithEvents = getRuntimeLogSteps(detail.node_results).find(
        (step) => step.events.length > 0
      );
      setExpandedRuntimeSteps(new Set(firstStepWithEvents ? [firstStepWithEvents.result_id] : []));
    } catch (err) {
      console.error("Error loading run detail:", err);
    }
  };

  const toggleRuntimeStep = (resultId: string) => {
    setExpandedRuntimeSteps((current) => {
      const next = new Set(current);
      if (next.has(resultId)) {
        next.delete(resultId);
      } else {
        next.add(resultId);
      }
      return next;
    });
  };

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => loadRuns()} />;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)] gap-6">
      <Card>
        <CardContent className="p-0">
          {runs.length === 0 ? (
            <div className="p-8 text-sm text-[var(--text-muted)]">No runs yet.</div>
          ) : (
            <div className="divide-y divide-[var(--border-subtle)]">
              {runs.map((run) => (
                <Button
                  key={run.run_id}
                  type="button"
                  variant="ghost"
                  className="w-full text-left transition-colors"
                  style={{
                    height: "auto",
                    display: "block",
                    padding: "1rem",
                    borderRadius: 0,
                  }}
                  onClick={() => void openRun(run.run_id)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {formatDate(run.created_at)}
                    </span>
                    <StatusBadge status={runBadgeStatus(run.status)} label={run.status} />
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">{run.run_id}</p>
                </Button>
              ))}
            </div>
          )}
          {hasMore && (
            <div className="p-4 border-t border-[var(--border-subtle)]">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadRuns(nextCursor)}
                disabled={loadingMore}
              >
                {loadingMore ? "Loading..." : "Load More"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-6">
          {selectedRun ? (
            <div className="space-y-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-[var(--text-primary)]">Run Detail</h2>
                  <p className="text-xs text-[var(--text-muted)]">{selectedRun.run.run_id}</p>
                </div>
                <StatusBadge status={runBadgeStatus(selectedRun.run.status)} label={selectedRun.run.status} />
              </div>
              <div>
                <h3 className="text-sm font-medium text-[var(--text-primary)] mb-2">Node Results</h3>
                <div className="space-y-2">
                  {selectedRun.node_results.map((result) => (
                    <div
                      key={result.result_id}
                      className="rounded-lg border border-[var(--border-subtle)] p-3"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm text-[var(--text-secondary)]">{result.node_id}</span>
                        <StatusBadge status={runBadgeStatus(result.status)} label={result.status} />
                      </div>
                      {result.error && <p className="mt-2 text-xs text-red-300">{result.error}</p>}
                    </div>
                  ))}
                </div>
              </div>
              <RuntimeEventTimeline
                steps={getRuntimeLogSteps(selectedRun.node_results)}
                expandedSteps={expandedRuntimeSteps}
                onToggle={toggleRuntimeStep}
                runBadgeStatus={runBadgeStatus}
              />
              <AutomationJsonTreeViewer label="Context" value={filterRuntimeLogContext(selectedRun.context)} />
            </div>
          ) : (
            <div className="text-sm text-[var(--text-muted)]">Select a run to inspect its context.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function RuntimeEventTimeline({
  steps,
  expandedSteps,
  onToggle,
  runBadgeStatus,
}: {
  steps: RuntimeLogStep[];
  expandedSteps: Set<string>;
  onToggle: (resultId: string) => void;
  runBadgeStatus: (status: AutomationRunStatus | AutomationNodeRunStatus) => RunBadgeStatus;
}) {
  const visibleSteps = steps.filter((step) => step.events.length > 0 || step.error);

  return (
    <section className="automation-runtime-events">
      <div className="automation-runtime-events__header">
        <div>
          <h3>Runtime events</h3>
          <p>Tool calls and lifecycle activity captured during this run.</p>
        </div>
      </div>

      {visibleSteps.length === 0 ? (
        <div className="automation-runtime-events__empty">No visible runtime events for this run.</div>
      ) : (
        <div className="automation-runtime-events__steps">
          {visibleSteps.map((step) => {
            const isExpanded = expandedSteps.has(step.result_id);
            return (
              <article key={step.result_id} className="automation-runtime-events__step">
                <Button
                  type="button"
                  variant="ghost"
                  className="automation-runtime-events__step-trigger"
                  onClick={() => onToggle(step.result_id)}
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                  <div>
                    <strong>{step.node_id}</strong>
                    <span>{step.events.length} runtime events</span>
                  </div>
                  <StatusBadge status={runBadgeStatus(step.status)} label={step.status} />
                </Button>

                {isExpanded && (
                  <div className="automation-runtime-events__body">
                    {step.error && (
                      <div className="automation-runtime-events__error">{step.error}</div>
                    )}
                    {step.events.map((event, index) => (
                      <div
                        key={`${step.result_id}-${event.event_type}-${index}`}
                        className="automation-runtime-events__event"
                      >
                        <div className="automation-runtime-events__event-meta">
                          <span className="automation-runtime-events__event-type">{event.event_type}</span>
                          {event.tool_name && <span>{event.tool_name}</span>}
                          {typeof event.success === "boolean" && (
                            <span>{event.success ? "success" : "failed"}</span>
                          )}
                        </div>
                        <pre>{event.content || "(empty event)"}</pre>
                      </div>
                    ))}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
