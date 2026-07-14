import type { AutomationRunNodeResult } from "../../../types/automation";

export interface RuntimeLogEvent {
  event_type: string;
  content: string;
  message_id?: string | null;
  tool_name?: string | null;
  tool_args?: Record<string, unknown> | null;
  success?: boolean | null;
}

export interface RuntimeToolCall {
  id: string;
  title: string;
  subtitle: string;
  toolName: string;
  args: Record<string, unknown> | null;
  result: unknown;
  success: boolean | null;
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
  return collectVisibleRuntimeEvents(output).map((event) => ({
    event_type: String(event.event_type),
    content: typeof event.content === "string" ? event.content : "",
    message_id: typeof event.message_id === "string" ? event.message_id : null,
    tool_name: typeof event.tool_name === "string" ? event.tool_name : null,
    tool_args: isRecord(event.tool_args) ? event.tool_args : null,
    success: typeof event.success === "boolean" ? event.success : null,
  }));
}

export function getLifecycleEvents(events: RuntimeLogEvent[]): RuntimeLogEvent[] {
  return events.filter(
    (event) => event.event_type.includes("LIFECYCLE") || event.event_type.includes("LIFECYLE")
  );
}

export function getToolCalls(events: RuntimeLogEvent[]): RuntimeToolCall[] {
  const calls: RuntimeToolCall[] = [];
  const pendingByTool = new Map<string, RuntimeLogEvent[]>();

  events.forEach((event, index) => {
    if (event.event_type === "TOOL_CALL_START") {
      const key = event.tool_name || `tool-${index}`;
      const queue = pendingByTool.get(key) ?? [];
      queue.push(event);
      pendingByTool.set(key, queue);
      return;
    }

    if (event.event_type !== "TOOL_CALL_RESULT") {
      return;
    }

    const key = event.tool_name || `tool-${index}`;
    const start = pendingByTool.get(key)?.shift();
    const args = start?.tool_args ?? event.tool_args ?? null;
    calls.push({
      id: `${key}-${index}`,
      title: toolCallTitle(event.tool_name, args),
      subtitle: toolCallSubtitle(event.tool_name, args),
      toolName: event.tool_name ?? "tool",
      args,
      result: parseToolResult(event),
      success: event.success ?? null,
    });
  });

  pendingByTool.forEach((queue, key) => {
    queue.forEach((start, index) => {
      calls.push({
        id: `${key}-pending-${index}`,
        title: toolCallTitle(start.tool_name, start.tool_args ?? null),
        subtitle: "Started, no result captured",
        toolName: start.tool_name ?? "tool",
        args: start.tool_args ?? null,
        result: { message: start.content || "Tool call started" },
        success: null,
      });
    });
  });

  return calls;
}

function toolCallTitle(toolName: string | null | undefined, args: Record<string, unknown> | null): string {
  if (toolName === "execute_skill_action" && args) {
    const skillId = typeof args.skill_id === "string" ? args.skill_id : "skill";
    const action = typeof args.action === "string" ? args.action : "action";
    return `${prettifyId(skillId)} · ${action}`;
  }
  if (toolName === "load_skill" && args && typeof args.skill_id === "string") {
    return `Load ${prettifyId(args.skill_id)}`;
  }
  return prettifyId(toolName ?? "Tool call");
}

function toolCallSubtitle(toolName: string | null | undefined, args: Record<string, unknown> | null): string {
  if (toolName === "execute_skill_action" && args) {
    const skillId = typeof args.skill_id === "string" ? args.skill_id : "unknown";
    const action = typeof args.action === "string" ? args.action : "unknown";
    return `${skillId} / ${action}`;
  }
  return toolName ?? "tool";
}

function prettifyId(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function parseToolResult(event: RuntimeLogEvent): unknown {
  const content = event.content.trim();
  if (!content) {
    return {};
  }
  if (content.startsWith("Error:")) {
    return { error: content.slice("Error:".length).trim() };
  }
  try {
    return JSON.parse(content);
  } catch {
    return { content };
  }
}

function collectVisibleRuntimeEvents(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectVisibleRuntimeEvents(item));
  }
  if (!isRecord(value)) {
    return [];
  }

  const directEvents = Array.isArray(value.events) ? value.events.filter(isVisibleRuntimeEvent) : [];
  const nestedEvents = Object.entries(value)
    .filter(([key]) => key !== "events")
    .flatMap(([, item]) => collectVisibleRuntimeEvents(item));
  return [...directEvents, ...nestedEvents];
}
