import { describe, expect, it } from "vitest";

import type { MCPCatalogTool, MCPSharingView } from "../../../../types/connectors";
import {
  canSave,
  groupTools,
  initialDraft,
  retiredTools,
  sharingLabel,
  toRequest,
  toolRisk,
  type SharingDraft,
} from "./sharingDraft";

const search: MCPCatalogTool = { name: "search", description: "Search issues", read_only: true, destructive: false };
const create: MCPCatalogTool = { name: "create_issue", description: "File a bug", read_only: false, destructive: false };
const remove: MCPCatalogTool = { name: "delete_issue", description: "Delete it", read_only: false, destructive: true };

function view(overrides: Partial<MCPSharingView> = {}): MCPSharingView {
  return {
    agent_id: "agent-1",
    mcp_id: "jira",
    connection_name: "Jira",
    sharing: { available_to: [], allowed_tools: [] },
    catalog: { tools: [remove, create, search], fetched_at: "2026-10-05T00:00:00Z" },
    disclaimer: { version: "2026-10-05", paragraphs: ["They act as you."] },
    ...overrides,
  };
}

const shared = view({ sharing: { available_to: ["visitor"], allowed_tools: ["create_issue", "gone_tool"] } });

describe("toolRisk", () => {
  it("reads the server's hints", () => {
    expect([search, create, remove].map(toolRisk)).toEqual(["read", "write", "destructive"]);
  });
});

describe("initialDraft", () => {
  it("starts a first share from the read-only tools only", () => {
    expect(initialDraft(view())).toEqual({ audiences: [], tools: ["search"], accepted: false });
  });

  it("continues an existing share without tools the server stopped offering", () => {
    expect(initialDraft(shared)).toEqual({ audiences: ["visitor"], tools: ["create_issue"], accepted: false });
  });

  it("asks for consent again on every save", () => {
    expect(initialDraft(shared).accepted).toBe(false);
  });
});

describe("retiredTools", () => {
  it("names shared tools the server no longer offers", () => {
    expect(retiredTools(shared)).toEqual(["gone_tool"]);
  });
});

describe("groupTools", () => {
  it("orders groups from harmless to destructive", () => {
    expect(groupTools([remove, create, search], "").map((group) => group.risk)).toEqual([
      "read",
      "write",
      "destructive",
    ]);
  });

  it("searches names and descriptions, dropping empty groups", () => {
    expect(groupTools([remove, create, search], "bug")).toEqual([{ risk: "write", tools: [create] }]);
  });
});

describe("canSave", () => {
  const draft = (overrides: Partial<SharingDraft>): SharingDraft => ({
    audiences: ["visitor"],
    tools: ["search"],
    accepted: true,
    ...overrides,
  });

  it("needs an audience, a tool and consent to share", () => {
    expect(canSave(draft({}), view())).toBe(true);
    expect(canSave(draft({ accepted: false }), view())).toBe(false);
    expect(canSave(draft({ tools: [] }), view())).toBe(false);
  });

  it("lets an owner stop sharing without consent, but not save nothing over nothing", () => {
    expect(canSave(draft({ audiences: [], accepted: false }), shared)).toBe(true);
    expect(canSave(draft({ audiences: [] }), view())).toBe(false);
  });
});

describe("toRequest", () => {
  it("sends the disclaimer version the owner accepted", () => {
    expect(toRequest({ audiences: ["a2a"], tools: ["search"], accepted: true }, view())).toEqual({
      available_to: ["a2a"],
      allowed_tools: ["search"],
      accept_disclaimer_version: "2026-10-05",
    });
  });

  it("stops sharing by naming nobody", () => {
    expect(toRequest({ audiences: [], tools: ["search"], accepted: false }, shared)).toEqual({
      available_to: [],
      allowed_tools: [],
    });
  });
});

describe("sharingLabel", () => {
  it("reads as a sentence fragment for the connector row", () => {
    expect(sharingLabel({ available_to: [], allowed_tool_count: 0, consent_outdated: false })).toBe("Only you");
    expect(sharingLabel({ available_to: ["a2a", "visitor"], allowed_tool_count: 3, consent_outdated: false })).toBe(
      "Widget visitors · A2A agents — 3 tools"
    );
  });
});
