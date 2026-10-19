import { describe, expect, it } from "vitest";
import type { AgentResponse } from "../../services/agents/AgentApiService";
import { agentSummary, hasAttachments, matchesQuery, recentAgents, sortAgents, timeAgo } from "./agentDiscovery";

function agent(name: string, extra: Partial<AgentResponse> = {}): AgentResponse {
  return {
    agent_id: name,
    agent_name: name,
    agent_architecture: "krishna-mini",
    agent_provider: "OpenAI",
    agent_model: null,
    agent_persona: `You are ${name}.`,
    account_id: "acc",
    owner_id: "me",
    created_by: "me",
    access: "owner",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    ...extra,
  };
}

describe("agentSummary", () => {
  it("prefers the description and falls back to the persona", () => {
    expect(agentSummary(agent("A", { agent_description: " Reviews contracts " }))).toBe("Reviews contracts");
    expect(agentSummary(agent("A", { agent_description: "  " }))).toBe("You are A.");
  });
});

describe("matchesQuery", () => {
  const contracts = agent("Contract Reviewer", { agent_description: "Flags risky clauses", agent_provider: "Anthropic" });

  it("needs every word, in any field, in any case", () => {
    expect(matchesQuery(contracts, "risky REVIEWER")).toBe(true);
    expect(matchesQuery(contracts, "anthropic clauses")).toBe(true);
    expect(matchesQuery(contracts, "risky invoices")).toBe(false);
  });

  it("matches everything for a blank query", () => {
    expect(matchesQuery(contracts, "   ")).toBe(true);
  });
});

describe("sortAgents", () => {
  const old = agent("Old", { last_used_at: "2026-02-01T00:00:00Z", use_count: 9, created_at: "2025-01-01T00:00:00Z" });
  const fresh = agent("Fresh", { last_used_at: "2026-03-01T00:00:00Z", use_count: 2, created_at: "2026-03-01T00:00:00Z" });
  const never = agent("Never");

  it("orders by each sort and leaves the input alone", () => {
    const input = [old, never, fresh];
    expect(sortAgents(input, "recent").map((a) => a.agent_name)).toEqual(["Fresh", "Old", "Never"]);
    expect(sortAgents(input, "used").map((a) => a.agent_name)).toEqual(["Old", "Fresh", "Never"]);
    expect(sortAgents(input, "newest").map((a) => a.agent_name)).toEqual(["Fresh", "Never", "Old"]);
    expect(sortAgents(input, "name").map((a) => a.agent_name)).toEqual(["Fresh", "Never", "Old"]);
    expect(input.map((a) => a.agent_name)).toEqual(["Old", "Never", "Fresh"]);
  });

  it("breaks ties A–Z", () => {
    const b = agent("B");
    const a = agent("A");
    expect(sortAgents([b, a], "used").map((x) => x.agent_name)).toEqual(["A", "B"]);
  });
});

describe("recentAgents", () => {
  it("leaves out agents never used and caps the list", () => {
    const used = ["A", "B", "C"].map((n, i) => agent(n, { last_used_at: `2026-03-0${i + 1}T00:00:00Z` }));
    expect(recentAgents([...used, agent("Never")], 2).map((a) => a.agent_name)).toEqual(["C", "B"]);
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-03-10T12:00:00Z");
  it("uses minutes, hours then days", () => {
    expect(timeAgo("2026-03-10T11:55:00Z", now)).toBe("5m ago");
    expect(timeAgo("2026-03-10T09:00:00Z", now)).toBe("3h ago");
    expect(timeAgo("2026-03-07T12:00:00Z", now)).toBe("3d ago");
  });
});

describe("hasAttachments", () => {
  const counts = { knowledge_bases: 2, connectors: 0, skills: 1 };

  it("needs every required attachment", () => {
    expect(hasAttachments(counts, [])).toBe(true);
    expect(hasAttachments(counts, ["knowledge_bases", "skills"])).toBe(true);
    expect(hasAttachments(counts, ["knowledge_bases", "connectors"])).toBe(false);
  });

  it("treats counts that haven't loaded as none", () => {
    expect(hasAttachments(undefined, ["skills"])).toBe(false);
    expect(hasAttachments(undefined, [])).toBe(true);
  });
});
