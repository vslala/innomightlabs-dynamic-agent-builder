import { useCallback, useEffect, useState } from "react";

import { Button, Card, CardContent, ErrorState, LoadingState, StatusBadge } from "../../../components/ui";
import { automationApiService } from "../../../services/automations";
import type {
  AutomationNodeRunStatus,
  AutomationRunDetailResponse,
  AutomationRunResponse,
  AutomationRunStatus,
  PaginatedResponse,
} from "../../../types/automation";
import { AutomationJsonTreeViewer } from "./components/AutomationJsonEditor";
import { useAutomationDetailContext } from "./types";

function runBadgeStatus(status: AutomationRunStatus | AutomationNodeRunStatus) {
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
    } catch (err) {
      console.error("Error loading run detail:", err);
    }
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
                <button
                  key={run.run_id}
                  type="button"
                  className="w-full text-left p-4 hover:bg-white/5 transition-colors"
                  onClick={() => void openRun(run.run_id)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {formatDate(run.created_at)}
                    </span>
                    <StatusBadge status={runBadgeStatus(run.status)} label={run.status} />
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">{run.run_id}</p>
                </button>
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
              <AutomationJsonTreeViewer label="Context" value={selectedRun.context} />
            </div>
          ) : (
            <div className="text-sm text-[var(--text-muted)]">Select a run to inspect its context.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
