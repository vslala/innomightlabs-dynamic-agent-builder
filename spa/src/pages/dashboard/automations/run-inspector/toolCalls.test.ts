import { describe, expect, it } from "vitest";

import type { AutomationStepEvent } from "../../../../types/automation";
import {
  actingArguments,
  argumentSummary,
  durationMs,
  matchesFilter,
  matchesQuery,
  parseToolResult,
  toolCallsFrom,
  toolCallTitle,
  toolCounts,
} from "./toolCalls";

const start = (id: string | null, url: string): AutomationStepEvent => ({
  event_type: "TOOL_CALL_START",
  content: "Calling fetch_page...",
  tool_call_id: id,
  tool_name: "fetch_page",
  tool_args: { url },
});

const result = (id: string | null, content: string, extra: Partial<AutomationStepEvent> = {}): AutomationStepEvent => ({
  event_type: "TOOL_CALL_RESULT",
  content,
  tool_call_id: id,
  tool_name: "fetch_page",
  success: true,
  ...extra,
});

describe("toolCallsFrom", () => {
  it("pairs each result with its own call by id, even when results arrive out of order", () => {
    const calls = toolCallsFrom([
      start("a", "https://a.example"),
      start("b", "https://b.example"),
      start("c", "https://c.example"),
      result("c", "page c"),
      result("a", "page a"),
      result("b", "page b"),
    ]);

    expect(calls.map((call) => [call.sequence, call.args.url, call.resultText])).toEqual([
      [1, "https://a.example", "page a"],
      [2, "https://b.example", "page b"],
      [3, "https://c.example", "page c"],
    ]);
  });

  it("keeps the order the agent asked for its tools, including calls that never returned", () => {
    const calls = toolCallsFrom([start("a", "https://a.example"), start("b", "https://b.example"), result("b", "page b")]);

    expect(calls.map((call) => [call.id, call.success])).toEqual([
      ["a", null],
      ["b", true],
    ]);
  });

  it("carries when the tool ran", () => {
    const [call] = toolCallsFrom([
      start("a", "https://a.example"),
      result("a", "page", { started_at: "2026-11-09T09:00:01Z", completed_at: "2026-11-09T09:00:03.500Z" }),
    ]);

    expect(call.startedAt).toBe("2026-11-09T09:00:01Z");
    expect(durationMs(call)).toBe(2500);
  });

  it("refreshes a call that starts again under the same id instead of adding one", () => {
    const calls = toolCallsFrom([start("a", "https://draft.example"), start("a", "https://final.example"), result("a", "ok")]);

    expect(calls).toHaveLength(1);
    expect(calls[0].args.url).toBe("https://final.example");
  });

  it("falls back to name order only for events recorded without an id", () => {
    const calls = toolCallsFrom([
      start(null, "https://a.example"),
      start(null, "https://b.example"),
      result(null, "page a"),
      result(null, "page b"),
    ]);

    expect(calls.map((call) => [call.args.url, call.resultText])).toEqual([
      ["https://a.example", "page a"],
      ["https://b.example", "page b"],
    ]);
  });

  it("shows the real tool behind a wrapper and keeps the wrapper for debugging", () => {
    const [call] = toolCallsFrom([
      {
        event_type: "TOOL_CALL_START",
        content: "",
        tool_call_id: "m",
        tool_name: "call_mcp_tool",
        tool_args: { server: "github", tool: "search_issues", arguments: { q: "bug" } },
        display_tool_name: "search_issues",
        display_tool_args: { q: "bug" },
      },
    ]);

    expect(call.toolName).toBe("search_issues");
    expect(call.args).toEqual({ q: "bug" });
    expect(call.wrapper?.toolName).toBe("call_mcp_tool");
  });
});

describe("presentation helpers", () => {
  const [skillCall] = toolCallsFrom([
    {
      event_type: "TOOL_CALL_START",
      content: "",
      tool_call_id: "s",
      tool_name: "execute_skill_action",
      tool_args: { skill_id: "web_research", action: "fetch_page", arguments: { url: "https://x.example" } },
    },
    result("s", '{"status": 200}', { tool_name: "execute_skill_action" }),
  ]);

  it("titles and summarises a skill action by what it acted on", () => {
    expect(toolCallTitle(skillCall)).toBe("Web Research · fetch_page");
    expect(actingArguments(skillCall)).toEqual({ url: "https://x.example" });
    expect(argumentSummary(skillCall)).toBe("url: https://x.example");
  });

  it("parses JSON results, reads errors, and keeps plain text whole", () => {
    expect(parseToolResult(skillCall)).toEqual({ kind: "json", value: { status: 200 } });
    const [failed] = toolCallsFrom([start("f", "u"), result("f", "Error: 404 not found", { success: false })]);
    expect(parseToolResult(failed)).toEqual({ kind: "error", message: "404 not found" });
    const [text] = toolCallsFrom([start("t", "u"), result("t", "a long page")]);
    expect(parseToolResult(text)).toEqual({ kind: "text", text: "a long page" });
  });

  it("filters and searches across tools, arguments and results", () => {
    const calls = toolCallsFrom([
      start("a", "https://a.example"),
      result("a", "nope", { success: false }),
      start("b", "https://pricing.example"),
      result("b", "plans"),
    ]);

    expect(calls.filter((call) => matchesFilter(call, { kind: "failed" })).map((call) => call.id)).toEqual(["a"]);
    expect(calls.filter((call) => matchesQuery(call, "PRICING")).map((call) => call.id)).toEqual(["b"]);
    expect(calls.filter((call) => matchesQuery(call, "plans")).map((call) => call.id)).toEqual(["b"]);
    expect(toolCounts(calls)).toEqual([{ toolName: "fetch_page", count: 2 }]);
  });
});
