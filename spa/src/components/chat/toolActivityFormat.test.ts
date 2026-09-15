import { describe, expect, it } from "vitest";

import type { ToolActivity } from "../../types/message";
import { toolActivityTitle } from "./toolActivityFormat";

function activity(overrides: Partial<ToolActivity>): ToolActivity {
  return {
    id: "activity-1",
    timestamp: new Date(),
    tool_name: "some_tool",
    status: "running",
    content: "",
    ...overrides,
  };
}

describe("toolActivityTitle", () => {
  it("renders a friendly label for a skill action", () => {
    const label = toolActivityTitle(
      activity({
        tool_name: "execute_skill_action",
        tool_args: { skill_id: "aura-recording:v1", action: "start_recording" },
      })
    );
    expect(label).toBe("Aura Recording · Start Recording");
  });

  it("renders a friendly label for loading a skill", () => {
    const label = toolActivityTitle(activity({ tool_name: "load_skill", tool_args: { skill_id: "aura-recording:v1" } }));
    expect(label).toBe("Loading Aura Recording");
  });

  it("renders a friendly label for a job check", () => {
    expect(toolActivityTitle(activity({ tool_name: "check_tool_job" }))).toBe("Checking task progress");
  });

  it("unwraps a call_mcp_tool activity to the real MCP tool name and args", () => {
    const label = toolActivityTitle(
      activity({
        tool_name: "call_mcp_tool",
        tool_args: { mcp_id: "atlassian", tool_name: "searchJiraIssuesUsingJql", arguments: { jql: "project = KAN" } },
        display_tool_name: "searchJiraIssuesUsingJql",
        display_tool_args: { jql: "project = KAN" },
      })
    );
    expect(label).toBe('searchJiraIssuesUsingJql({ jql: "project = KAN" })');
  });

  it("falls back to keys-only when the value summary would be too long", () => {
    const label = toolActivityTitle(
      activity({
        tool_name: "search_code",
        tool_args: { query: "a".repeat(60), repository: "innomightlabs-prod" },
      })
    );
    expect(label).toBe("search_code({ query, repository })");
  });

  it("never renders a sensitive-looking argument's value", () => {
    const label = toolActivityTitle(
      activity({ tool_name: "connect_service", tool_args: { api_key: "sk-super-secret", region: "us-east-1" } })
    );
    expect(label).toBe('connect_service({ api_key, region: "us-east-1" })');
  });

  it("renders a bare call when no args are present", () => {
    expect(toolActivityTitle(activity({ tool_name: "list_mcp_tools" }))).toBe("list_mcp_tools()");
  });

  it.each([
    ["core_memory_read", { block: "persona" }, "Reading core memory (persona)"],
    ["core_memory_read", {}, "Reading core memory"],
    ["core_memory_append", { block: "human", content: "Prefers dark mode" }, "Appending to core memory (human)"],
    ["core_memory_list_blocks", {}, "Listing core memory blocks"],
    ["archival_memory_insert", { content: "..." }, "Storing to archival memory"],
    ["archival_memory_search", { query: "pricing tiers" }, 'Searching archival memory for "pricing tiers"'],
    ["archival_memory_search", {}, "Searching archival memory"],
    ["recall_conversation", { page: 2 }, "Recalling earlier conversation"],
    ["knowledge_base_search", { query: "refund policy" }, 'Searching the knowledge base for "refund policy"'],
    ["wait", {}, "Waiting"],
    ["wait", { reason: "job still running" }, "Waiting — Job still running"],
  ] as const)("renders a plain-English label for %s", (toolName, args, expected) => {
    expect(toolActivityTitle(activity({ tool_name: toolName, tool_args: args }))).toBe(expected);
  });

  it("mentions the target line and block when replacing a core memory line", () => {
    const label = toolActivityTitle(
      activity({ tool_name: "core_memory_replace", tool_args: { block: "persona", line_number: 3, new_content: "x" } })
    );
    expect(label).toBe("Replacing line 3 in core memory (persona)");
  });

  it("mentions the target line and block when deleting a core memory line", () => {
    const label = toolActivityTitle(
      activity({ tool_name: "core_memory_delete", tool_args: { block: "human", line_number: 5 } })
    );
    expect(label).toBe("Deleting line 5 from core memory (human)");
  });

  it("does not phrase an MCP wrapper call as plain English, since we don't control the tool name", () => {
    const label = toolActivityTitle(activity({ tool_name: "list_mcp_tools", tool_args: { mcp_id: "atlassian" } }));
    expect(label).toBe('list_mcp_tools({ mcp_id: "atlassian" })');
  });

  it("does not throw and still renders a label for an unexpected args shape", () => {
    const label = toolActivityTitle(
      activity({ tool_name: "weird_tool", tool_args: { nested: { a: 1 }, list: [1, 2, 3] } })
    );
    expect(label).toBe("weird_tool({ nested, list })");
  });
});
