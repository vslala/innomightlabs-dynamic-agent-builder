/**
 * The tool calls of one step result, loaded when the step is inspected.
 *
 * They are fetched on their own (not with the run) because a busy agent step's log can be large and the run
 * itself is polled every second and a half while it executes. A result is final once it exists, so each one is
 * fetched once.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { automationApiService } from "../../../../services/automations";
import type { AutomationRunNodeResult, AutomationStepEvent } from "../../../../types/automation";
import { toolCallsFrom, type ToolCall } from "./toolCalls";

export interface StepToolCalls {
  calls: ToolCall[];
  /** The events as recorded, for the raw view. */
  events: AutomationStepEvent[];
  loading: boolean;
  error: string | null;
  retry: () => void;
}

interface Loaded {
  key: string;
  events: AutomationStepEvent[];
  error: string | null;
}

export function useStepToolCalls(automationId: string, result: AutomationRunNodeResult | null): StepToolCalls {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [attempt, setAttempt] = useState(0);

  const runId = result?.run_id;
  const resultId = result && result.tool_call_count > 0 ? result.result_id : null;
  const key = resultId ? `${resultId}#${attempt}` : null;

  useEffect(() => {
    if (!key || !runId || !resultId) return;
    let current = true;
    automationApiService
      .getStepEvents(automationId, runId, resultId)
      .then((response) => current && setLoaded({ key, events: response.events, error: null }))
      .catch((error: unknown) => current && setLoaded({ key, events: [], error: errorMessage(error) }));
    return () => {
      current = false;
    };
  }, [automationId, key, resultId, runId]);

  const fresh = loaded !== null && loaded.key === key;
  const events = useMemo(() => (fresh ? loaded.events : []), [fresh, loaded]);
  const calls = useMemo(() => toolCallsFrom(events), [events]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  return {
    calls,
    events,
    loading: key !== null && !fresh,
    error: fresh ? loaded.error : null,
    retry,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : "Couldn't load this step's activity.";
}
