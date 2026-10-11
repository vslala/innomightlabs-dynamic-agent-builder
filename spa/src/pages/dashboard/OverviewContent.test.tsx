import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { OverviewContent, type DashboardData } from "./OverviewContent";

const empty: DashboardData = {
  agents: [], conversations: [], automations: [], knowledgeBases: [], connectors: [], mcpConnections: [],
};

function render(data: Partial<DashboardData>) {
  return renderToStaticMarkup(
    <MemoryRouter><OverviewContent data={{ ...empty, ...data }} /></MemoryRouter>,
  );
}

const now = new Date().toISOString();
const agent = {
  agent_id: "a1", agent_name: "Support bot", agent_provider: "anthropic", agent_model: "claude",
  is_agent2agent_enabled: true, created_at: now, updated_at: now,
} as unknown as DashboardData["agents"][number];
const conversation = {
  conversation_id: "c1", agent_id: "a1", title: "Refund question", created_at: now, updated_at: now,
} as unknown as DashboardData["conversations"][number];

describe("dashboard overview", () => {
  it("leads a new workspace to its first agent and the setup steps", () => {
    const html = render({});
    expect(html).toContain("Create your first agent");
    expect(html).toContain("0 of 5 steps done");
    expect(html).not.toContain("Recent work");
    expect(html).toContain("What&#x27;s new");
  });

  it("shows the summary figures and recent work once there is something to show", () => {
    const html = render({ agents: [agent], conversations: [conversation] });
    expect(html).not.toContain("Create your first agent");
    expect(html).toContain("Recent work");
    expect(html).toContain("Support bot");
    expect(html).toContain("Refund question");
    expect(html).toContain('href="/dashboard/agents/a1"');
    expect(html).toContain("1 open to A2A");
    expect(html).toContain("2 of 5 steps done");
  });

  it("drops the setup card once every step is done, and keeps one link per figure", () => {
    const html = render({
      agents: [agent], conversations: [conversation],
      automations: [{ status: "active" }] as unknown as DashboardData["automations"],
      knowledgeBases: [{ total_vectors: 1200 }] as unknown as DashboardData["knowledgeBases"],
      connectors: [{ connected: true }] as unknown as DashboardData["connectors"],
    });
    expect(html).not.toContain("Getting started");
    expect(html).toContain("1.2K indexed vectors");
    for (const to of ["/dashboard/agents", "/dashboard/conversations", "/dashboard/automations", "/dashboard/knowledge-bases"]) {
      expect(html).toContain(`href="${to}"`);
    }
  });
});
