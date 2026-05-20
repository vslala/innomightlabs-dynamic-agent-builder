import type { AutomationRunNodeResult } from "../../../types/automation";

export interface RuntimeLogEvent {
  event_type: string;
  content: string;
  message_id?: string | null;
  tool_name?: string | null;
  success?: boolean | null;
}

export interface RuntimeLogStep {
  result_id: string;
  node_id: string;
  status: AutomationRunNodeResult["status"];
  error?: string | null;
  events: RuntimeLogEvent[];
}

export const VISIBLE_RUNTIME_EVENT_TYPES = new Set([
  "TOOL_CALL_START",
  "TOOL_CALL_RESULT",
  "LIFECYCLE_NOTIFICATION",
  "LIFECYLE_NOTIFICATION",
]);

export function filterRuntimeLogContext(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => filterRuntimeLogContext(item));
  }

  if (!isRecord(value)) {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => {
      if (key === "events" && Array.isArray(item)) {
        return [
          key,
          item
            .filter((event) => isVisibleRuntimeEvent(event))
            .map((event) => filterRuntimeLogContext(event)),
        ];
      }

      return [key, filterRuntimeLogContext(item)];
    })
  );
}

export function getRuntimeLogSteps(nodeResults: AutomationRunNodeResult[]): RuntimeLogStep[] {
  return nodeResults.map((result) => ({
    result_id: result.result_id,
    node_id: result.node_id,
    status: result.status,
    error: result.error,
    events: getVisibleRuntimeEvents(result.output),
  }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isVisibleRuntimeEvent(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false;
  }

  return typeof value.event_type === "string" && VISIBLE_RUNTIME_EVENT_TYPES.has(value.event_type);
}

function getVisibleRuntimeEvents(output: Record<string, unknown>): RuntimeLogEvent[] {
  const events = output.events;
  if (!Array.isArray(events)) {
    return [];
  }

  return events.filter(isVisibleRuntimeEvent).map((event) => ({
    event_type: String(event.event_type),
    content: typeof event.content === "string" ? event.content : "",
    message_id: typeof event.message_id === "string" ? event.message_id : null,
    tool_name: typeof event.tool_name === "string" ? event.tool_name : null,
    success: typeof event.success === "boolean" ? event.success : null,
  }));
}
