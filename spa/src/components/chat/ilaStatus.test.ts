import { describe, expect, it } from "vitest";
import type { ToolActivity } from "../../types/message";
import { holdDelay, ilaStatus, MIN_SHOWN_MS, pageLabel } from "./ilaStatus";

function activity(
  tool_name: string,
  status: ToolActivity["status"],
  tool_args?: Record<string, unknown>,
): ToolActivity {
  return { id: tool_name, timestamp: new Date(), tool_name, status, content: "", tool_args };
}

describe("what Ila is doing", () => {
  it("says the running tool in plain words", () => {
    expect(ilaStatus([activity("plan_blueprint", "running")], true)).toBe("Planning your blueprint");
    expect(ilaStatus([activity("show_form", "success"), activity("apply_blueprint", "running")], true)).toBe("Building it");
    expect(ilaStatus([activity("get_build_status", "running")], true)).toBe("Checking on your build");
  });

  it("names what she is reading, never a page id", () => {
    expect(ilaStatus([activity("open_pages", "running", { page_ids: ["kind/Agent"] })], true)).toBe("Reading about agents");
    expect(
      ilaStatus([activity("open_pages", "running", { page_ids: ["kind/KnowledgeBase", "skill/send_email", "recipe/site-agent"] })], true),
    ).toBe("Reading about knowledge bases, the Send Email skill and more");
    expect(ilaStatus([activity("open_pages", "running", { page_ids: ["account/Agent/abc/instructions"] })], true)).toBe(
      "Reading about your agent's instructions",
    );
  });

  it("says what she is searching for, and where", () => {
    expect(ilaStatus([activity("search_book", "running", { query: "demo requests" })], true)).toBe(
      "Searching what I can build for “demo requests”",
    );
    expect(ilaStatus([activity("search_book", "running", { query: "innomight", prefix: "account/Agent" })], true)).toBe(
      "Searching your account for “innomight”",
    );
    expect(ilaStatus([activity("search_book", "running", { prefix: "account/LeadForm" })], true)).toBe(
      "Looking through your lead forms",
    );
  });

  it("says what she is adding to the draft", () => {
    expect(ilaStatus([activity("add_to_draft", "running", { page_id: "account/Agent/abc" })], true)).toBe(
      "Adding your agent to the draft",
    );
  });

  it("never fails on odd arguments, or on a tool she doesn't know", () => {
    expect(ilaStatus([activity("open_pages", "running", { page_ids: 7 })], true)).toBe("Reading up");
    expect(ilaStatus([activity("search_book", "running")], true)).toBe("Searching");
    expect(ilaStatus([activity("a_new_tool", "running")], true)).toBe("Working on it");
  });

  it("is thinking between tools, and quiet once the turn ends", () => {
    expect(ilaStatus([activity("plan_blueprint", "success")], true)).toBe("Thinking");
    expect(ilaStatus([], true)).toBe("Thinking");
    expect(ilaStatus([activity("plan_blueprint", "success")], false)).toBeNull();
  });

  it("shows the latest of several running tools", () => {
    expect(ilaStatus([activity("open_pages", "running", { page_ids: ["kind/Agent"] }), activity("show_form", "running")], true)).toBe(
      "Preparing a few questions",
    );
  });
});

describe("page labels", () => {
  it.each([
    ["kind/Agent", "agents"],
    ["kind/LeadForm", "lead forms"],
    ["skill/lead_capture", "the Lead Capture skill"],
    ["recipe/lead-qualifier", "the Lead Qualifier recipe"],
    ["guide/blueprint", "how blueprints are written"],
    ["account/Automation", "your automations"],
    ["account/Automation/abc", "your automation"],
  ])("%s reads as %s", (id, label) => {
    expect(pageLabel(id)).toBe(label);
  });
});

describe("holding a line long enough to read", () => {
  it("waits out what is left of the minimum, and never waits longer", () => {
    expect(holdDelay(1000, 1000)).toBe(MIN_SHOWN_MS);
    expect(holdDelay(1000, 1300)).toBe(MIN_SHOWN_MS - 300);
    expect(holdDelay(1000, 1000 + MIN_SHOWN_MS)).toBe(0);
    expect(holdDelay(1000, 9000)).toBe(0);
  });
});
