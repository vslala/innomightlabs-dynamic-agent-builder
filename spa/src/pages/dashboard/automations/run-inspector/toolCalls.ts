/**
 * A step's recorded tool events as the moves its agent made: one entry per tool call, in the order the agent
 * asked for them, each with its arguments and the result that came back.
 *
 * A start and its result are paired by `tool_call_id`, never by tool name: an agent that fetches three pages
 * makes three calls to the same tool, and pairing by name is what used to attach a result to the wrong arguments.
 * Only events recorded without an id (very old runs) fall back to name order.
 */

import type { AutomationStepEvent } from "../../../../types/automation";

export interface ToolCall {
  /** `tool_call_id`, or a stand-in for events recorded without one. */
  id: string;
  /** 1-based position in the order the agent asked for its tools. */
  sequence: number;
  /** The tool the agent reached, unwrapped from wrappers such as `call_mcp_tool`. */
  toolName: string;
  args: Record<string, unknown>;
  /** The tool the model actually called, when a wrapper was unwrapped for display. */
  wrapper: { toolName: string; args: Record<string, unknown> } | null;
  /** null until a result is recorded. */
  success: boolean | null;
  /** The result exactly as recorded. */
  resultText: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

const START = "TOOL_CALL_START";
const RESULT = "TOOL_CALL_RESULT";

export function toolCallsFrom(events: AutomationStepEvent[]): ToolCall[] {
  const calls: ToolCall[] = [];
  const byId = new Map<string, ToolCall>();
  /** Calls started without an id and still waiting for a result, oldest first. */
  const openWithoutId: ToolCall[] = [];

  const add = (event: AutomationStepEvent, index: number): ToolCall => {
    const call = newCall(event, index, calls.length + 1);
    calls.push(call);
    if (event.tool_call_id) byId.set(event.tool_call_id, call);
    return call;
  };

  events.forEach((event, index) => {
    const known = event.tool_call_id ? byId.get(event.tool_call_id) : undefined;
    if (event.event_type === START) {
      if (known) {
        // The same call started again (resumed after consent): refresh it rather than add another
        Object.assign(known, identity(event));
      } else {
        const call = add(event, index);
        if (!event.tool_call_id) openWithoutId.push(call);
      }
    } else if (event.event_type === RESULT) {
      const call = known ?? (event.tool_call_id ? undefined : takeOpen(openWithoutId, event.tool_name)) ?? add(event, index);
      call.success = event.success ?? null;
      call.resultText = event.content;
      call.startedAt = event.started_at ?? null;
      call.completedAt = event.completed_at ?? null;
    }
  });
  return calls;
}

function takeOpen(open: ToolCall[], toolName: string | null | undefined): ToolCall | undefined {
  const index = open.findIndex((call) => call.toolName === toolName || call.wrapper?.toolName === toolName);
  return index === -1 ? undefined : open.splice(index, 1)[0];
}

function newCall(event: AutomationStepEvent, index: number, sequence: number): ToolCall {
  return {
    id: event.tool_call_id || `event-${index}`,
    sequence,
    ...identity(event),
    success: null,
    resultText: null,
    startedAt: null,
    completedAt: null,
  };
}

/** What was called and with what. A result event carries the display name but not the arguments. */
function identity(event: AutomationStepEvent): Pick<ToolCall, "toolName" | "args" | "wrapper"> {
  const toolName = event.tool_name || "tool";
  const args = event.tool_args ?? {};
  const displayName = event.display_tool_name || toolName;
  const displayArgs = event.display_tool_args ?? args;
  const unwrapped = displayName !== toolName;
  return {
    toolName: displayName,
    args: displayArgs,
    wrapper: unwrapped ? { toolName, args } : null,
  };
}

/** "Web Research · fetch_page" for a skill action, "Search Memory" for a plain tool. */
export function toolCallTitle(call: ToolCall): string {
  const { skill_id: skillId, action } = call.args;
  if (call.toolName === "execute_skill_action" && typeof skillId === "string") {
    return `${humanize(skillId)} · ${typeof action === "string" ? action : "action"}`;
  }
  if (call.toolName === "load_skill" && typeof skillId === "string") return `Load ${humanize(skillId)}`;
  return humanize(call.toolName);
}

/**
 * The arguments the tool acted on: a skill action's own `arguments`, not the envelope naming the skill
 * (the title already says which skill and action).
 */
export function actingArguments(call: ToolCall): Record<string, unknown> {
  const inner = call.args.arguments;
  if (call.toolName === "execute_skill_action" && isRecord(inner)) return inner;
  return call.args;
}

/** One line of what the call was about, for the timeline: `url: https://…`. */
export function argumentSummary(call: ToolCall): string {
  return Object.entries(actingArguments(call))
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join(" · ");
}

export type ToolResult =
  | { kind: "none" }
  | { kind: "error"; message: string }
  | { kind: "json"; value: unknown }
  | { kind: "text"; text: string };

export function parseToolResult(call: ToolCall): ToolResult {
  const text = call.resultText;
  if (text === null) return { kind: "none" };
  const trimmed = text.trim();
  if (call.success === false && trimmed.startsWith("Error:")) {
    return { kind: "error", message: trimmed.slice("Error:".length).trim() };
  }
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return { kind: "json", value: JSON.parse(trimmed) };
    } catch {
      // Not JSON after all (or cut off): show it as text
    }
  }
  return call.success === false ? { kind: "error", message: trimmed } : { kind: "text", text };
}

export function durationMs(call: ToolCall): number | null {
  if (!call.startedAt || !call.completedAt) return null;
  const ms = Date.parse(call.completedAt) - Date.parse(call.startedAt);
  return Number.isFinite(ms) && ms >= 0 ? ms : null;
}

export type ToolCallFilter = { kind: "all" } | { kind: "failed" } | { kind: "open" } | { kind: "tool"; toolName: string };

export function matchesFilter(call: ToolCall, filter: ToolCallFilter): boolean {
  switch (filter.kind) {
    case "all":
      return true;
    case "failed":
      return call.success === false;
    case "open":
      return call.success === null;
    case "tool":
      return call.toolName === filter.toolName;
  }
}

/** Case-insensitive search over what a person would look for: the tool, its arguments and its result. */
export function matchesQuery(call: ToolCall, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [call.toolName, toolCallTitle(call), JSON.stringify(call.args), call.resultText ?? ""];
  return haystack.some((text) => text.toLowerCase().includes(needle));
}

/** Distinct tools in first-use order, with how often each was called: the timeline's filter chips. */
export function toolCounts(calls: ToolCall[]): { toolName: string; count: number }[] {
  const counts = new Map<string, number>();
  calls.forEach((call) => counts.set(call.toolName, (counts.get(call.toolName) ?? 0) + 1));
  return [...counts].map(([toolName, count]) => ({ toolName, count }));
}

/** A value as a person reads it: strings as they are, anything else as indented JSON. */
export function asText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? String(value);
}

export function humanize(id: string): string {
  return id.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
