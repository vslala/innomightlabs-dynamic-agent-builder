/**
 * Run history plus the selected run, shared by the runs drawer and the chain.
 *
 * The selected run is what puts the workspace in run view: every step card reads
 * its own result from `resultsByNodeId`, so the data a step produced is visible
 * in the same place its parameters are edited.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { automationApiService } from "../../../../services/automations";
import type {
  AutomationRunDetailResponse,
  AutomationRunNodeResult,
  AutomationRunResponse,
} from "../../../../types/automation";

const RUN_POLL_INTERVAL_MS = 1500;
const RUNS_PAGE_SIZE = 20;

export const TERMINAL_RUN_STATUSES = new Set(["succeeded", "failed", "cancelled"]);

export interface AutomationRunsState {
  runs: AutomationRunResponse[];
  hasMore: boolean;
  loadingRuns: boolean;
  loadingMore: boolean;
  runsError: string | null;
  selectedRunId: string | null;
  detail: AutomationRunDetailResponse | null;
  detailLoading: boolean;
  resultsByNodeId: Map<string, AutomationRunNodeResult>;
  context: Record<string, unknown> | null;
  isRunning: boolean;
  startError: string | null;
  loadRuns: () => Promise<void>;
  loadMore: () => Promise<void>;
  selectRun: (runId: string | null) => void;
  startTestRun: (input: Record<string, unknown>) => Promise<AutomationRunResponse | null>;
}

export function useAutomationRuns(automationId: string | undefined): AutomationRunsState {
  const [runs, setRuns] = useState<AutomationRunResponse[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AutomationRunDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const mountedRef = useRef(true);
  const pollRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      pollRef.current += 1;
    };
  }, []);

  const loadRuns = useCallback(async () => {
    if (!automationId) return;
    setLoadingRuns(true);
    setRunsError(null);
    try {
      const page = await automationApiService.listRuns(automationId, RUNS_PAGE_SIZE);
      if (!mountedRef.current) return;
      setRuns(page.items);
      setCursor(page.next_cursor ?? null);
      setHasMore(page.has_more);
    } catch (error) {
      if (mountedRef.current) setRunsError(errorMessage(error));
    } finally {
      if (mountedRef.current) setLoadingRuns(false);
    }
  }, [automationId]);

  const loadMore = useCallback(async () => {
    if (!automationId || !cursor) return;
    setLoadingMore(true);
    try {
      const page = await automationApiService.listRuns(automationId, RUNS_PAGE_SIZE, cursor);
      if (!mountedRef.current) return;
      setRuns((current) => [...current, ...page.items]);
      setCursor(page.next_cursor ?? null);
      setHasMore(page.has_more);
    } catch (error) {
      if (mountedRef.current) setRunsError(errorMessage(error));
    } finally {
      if (mountedRef.current) setLoadingMore(false);
    }
  }, [automationId, cursor]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  /** Follow one run until it reaches a terminal status, refreshing the chain as it goes. */
  const followRun = useCallback(
    async (runId: string) => {
      if (!automationId) return;
      const pollId = pollRef.current + 1;
      pollRef.current = pollId;
      setDetailLoading(true);
      try {
        let next = await automationApiService.getRun(automationId, runId);
        while (pollRef.current === pollId && mountedRef.current) {
          setDetail(next);
          setIsRunning(!TERMINAL_RUN_STATUSES.has(next.run.status));
          if (TERMINAL_RUN_STATUSES.has(next.run.status)) break;
          await sleep(RUN_POLL_INTERVAL_MS);
          if (pollRef.current !== pollId) return;
          next = await automationApiService.getRun(automationId, runId);
        }
        if (pollRef.current === pollId && mountedRef.current) {
          setRuns((current) =>
            current.map((run) => (run.run_id === next.run.run_id ? next.run : run))
          );
        }
      } catch (error) {
        if (pollRef.current === pollId && mountedRef.current) setRunsError(errorMessage(error));
      } finally {
        if (pollRef.current === pollId && mountedRef.current) {
          setDetailLoading(false);
          setIsRunning(false);
        }
      }
    },
    [automationId]
  );

  const selectRun = useCallback(
    (runId: string | null) => {
      setSelectedRunId(runId);
      if (!runId) {
        pollRef.current += 1;
        setDetail(null);
        return;
      }
      void followRun(runId);
    },
    [followRun]
  );

  /**
   * Start a run and add it to the list. Selecting it is the caller's job, so
   * that run selection has exactly one owner (the `run` query parameter).
   */
  const startTestRun = useCallback(
    async (input: Record<string, unknown>) => {
      if (!automationId) return null;
      setStartError(null);
      setIsRunning(true);
      try {
        const run = await automationApiService.testRun(automationId, { input });
        if (!mountedRef.current) return run;
        setRuns((current) => [run, ...current]);
        return run;
      } catch (error) {
        if (mountedRef.current) {
          setStartError(errorMessage(error));
          setIsRunning(false);
        }
        return null;
      }
    },
    [automationId]
  );

  const resultsByNodeId = useMemo(() => {
    const byNode = new Map<string, AutomationRunNodeResult>();
    detail?.node_results.forEach((result) => byNode.set(result.node_id, result));
    return byNode;
  }, [detail]);

  return {
    runs,
    hasMore,
    loadingRuns,
    loadingMore,
    runsError,
    selectedRunId,
    detail,
    detailLoading,
    resultsByNodeId,
    context: (detail?.context as Record<string, unknown> | undefined) ?? null,
    isRunning,
    startError,
    loadRuns,
    loadMore,
    selectRun,
    startTestRun,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}
