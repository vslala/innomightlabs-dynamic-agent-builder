import { useCallback, useEffect, useState } from "react";
import "./styles.css";

import {
  Button,
  Card,
  CardContent,
  ErrorState,
  AccordionPanel,
  JsonTreeViewer,
  LoadingState,
  StatusBadge,
  StepInspector,
  type StepInspectorItem,
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
import {
  getLifecycleEvents,
  getRuntimeLogSteps,
  getToolCalls,
  type RuntimeLogEvent,
  type RuntimeToolCall,
} from "./runDisplay";
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
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
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
      setSelectedStepId(detail.node_results[0]?.result_id ?? null);
    } catch (err) {
      console.error("Error loading run detail:", err);
    }
  };

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => loadRuns()} />;

  const selectedRunStepItems = selectedRun ? toStepInspectorItems(selectedRun.node_results) : [];
  const selectedStep =
    selectedRunStepItems.find((step) => step.id === selectedStepId) ?? selectedRunStepItems[0] ?? null;
  const selectedNodeResult = selectedRun?.node_results.find((result) => result.result_id === selectedStep?.id) ?? null;

  return (
    <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,24rem)_minmax(0,1fr)]">
      <Card className="xl:max-h-[calc(100vh-13rem)] xl:overflow-hidden">
        <CardContent className="p-0 xl:flex xl:max-h-[calc(100vh-13rem)] xl:flex-col">
          {runs.length === 0 ? (
            <div className="p-8 text-sm text-[var(--text-muted)]">No runs yet.</div>
          ) : (
            <div className="min-h-0 divide-y divide-[var(--border-subtle)] xl:overflow-y-auto">
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
              <StepInspector
                title="Step inputs and outputs"
                description="Steps are shown in execution order. Select one to inspect input, output, tool calls, and lifecycle events."
                steps={selectedRunStepItems}
                emptyMessage="No node input or output was captured for this run."
                selectedStepId={selectedStepId}
                onSelectedStepChange={setSelectedStepId}
                showDetails={false}
              />
            </div>
          ) : (
            <div className="text-sm text-[var(--text-muted)]">Select a run to inspect its context.</div>
          )}
        </CardContent>
      </Card>

      {selectedRun && selectedStep && (
        <Card className="xl:col-span-2">
          <CardContent className="p-6">
            {selectedNodeResult && <RunStepAnalysis result={selectedNodeResult} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function toStepInspectorItems(
  results: AutomationRunDetailResponse["node_results"]
): StepInspectorItem[] {
  return results.map((result) => ({
    id: result.result_id,
    title: result.node_id,
    subtitle: result.result_id,
    input: result.input,
    output: extractOutputResponse(result.output),
    error: result.error,
    status: <StatusBadge status={runBadgeStatus(result.status)} label={result.status} />,
    meta: result.completed_at ? (
      <span className="text-xs text-[var(--text-muted)]">{formatDate(result.completed_at)}</span>
    ) : null,
  }));
}

function omitRuntimeEvents(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => omitRuntimeEvents(item));
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => key !== "events")
      .map(([key, item]) => [key, omitRuntimeEvents(item)])
  );
}

function RunStepAnalysis({ result }: { result: AutomationRunDetailResponse["node_results"][number] }) {
  const events = getRuntimeLogSteps([result])[0]?.events ?? [];
  const outputResponse = extractOutputResponse(result.output);
  return (
    <section className="automation-run-analysis">
      <div className="automation-run-analysis__node">
        <div>
          <h3>{result.node_id}</h3>
          <p>{result.result_id}</p>
        </div>
        <StatusBadge status={runBadgeStatus(result.status)} label={result.status} />
      </div>

      {result.error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">
          {result.error}
        </div>
      )}

      <div className="automation-run-analysis__grid">
        <JsonTreeViewer label="Input" value={result.input ?? {}} maxHeight="42rem" />
        <OutputLog events={events} output={outputResponse} />
      </div>
    </section>
  );
}

function OutputLog({ events, output }: { events: RuntimeLogEvent[]; output: unknown }) {
  const toolCalls = getToolCalls(events);
  const lifecycleEvents = getLifecycleEvents(events);
  return (
    <section className="automation-output-log">
      <div className="automation-output-log__header">
        <h3>Output log</h3>
        <p>Lifecycle, tool calls, and final node response.</p>
      </div>
      <LifecyclePanel events={lifecycleEvents} />
      <ToolCallPanel calls={toolCalls} />
      <JsonTreeViewer label="Output response" value={output ?? {}} maxHeight="32rem" />
    </section>
  );
}

function LifecyclePanel({ events }: { events: RuntimeLogEvent[] }) {
  return (
    <AccordionPanel
      defaultOpen={events.length > 0}
      title={<span className="text-sm font-semibold text-[var(--text-primary)]">Lifecycle</span>}
      subtitle={`${events.length} event${events.length === 1 ? "" : "s"}`}
    >
      {events.length === 0 ? (
        <div className="automation-runtime-events__empty">No lifecycle events were captured for this step.</div>
      ) : (
        <ol className="automation-runtime-events__list">
          {events.map((event, index) => (
            <li key={`${event.event_type}-${index}`} className="automation-runtime-events__list-item">
              <span>{index + 1}</span>
              <p>{event.content || event.event_type}</p>
            </li>
          ))}
        </ol>
      )}
    </AccordionPanel>
  );
}

function ToolCallPanel({ calls }: { calls: RuntimeToolCall[] }) {
  return (
    <AccordionPanel
      defaultOpen={calls.length > 0}
      title={<span className="text-sm font-semibold text-[var(--text-primary)]">Tool calls</span>}
      subtitle={`${calls.length} call${calls.length === 1 ? "" : "s"}`}
    >
      {calls.length === 0 ? (
        <div className="automation-runtime-events__empty">No tool calls were captured for this step.</div>
      ) : (
        <div className="automation-runtime-events__accordions">
          {calls.map((call, index) => (
            <AccordionPanel
              key={call.id}
              defaultOpen={index === 0}
              title={<span className="text-sm font-semibold text-[var(--text-primary)]">{call.title}</span>}
              subtitle={call.subtitle}
              trailing={
                call.success === null ? (
                  <StatusBadge status="info" label="started" />
                ) : (
                  <StatusBadge status={call.success ? "success" : "failed"} label={call.success ? "success" : "failed"} />
                )
              }
            >
              <div className="grid min-w-0 gap-4">
                {call.args && <JsonTreeViewer label="Arguments" value={call.args} maxHeight="18rem" />}
                <JsonTreeViewer label="Tool response" value={call.result} maxHeight="26rem" />
              </div>
            </AccordionPanel>
          ))}
        </div>
      )}
    </AccordionPanel>
  );
}

function extractOutputResponse(output: Record<string, unknown>): unknown {
  const cleaned = omitRuntimeEvents(output);
  if (!cleaned || typeof cleaned !== "object") {
    return cleaned;
  }
  const record = cleaned as Record<string, unknown>;
  if (record.result && typeof record.result === "object") {
    const result = record.result as Record<string, unknown>;
    if ("response_text" in result) {
      return { response_text: result.response_text };
    }
    return result;
  }
  return cleaned;
}
