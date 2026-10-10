import { describe, expect, it } from "vitest";
import { ILA_AGENT_ID, agentDisplayName, chatPath, showsToolActivity } from "./ila";

describe("Ila's chat routes", () => {
  it("sends Ila's conversations to the builder and everyone else's to their agent", () => {
    expect(chatPath(ILA_AGENT_ID, "c1")).toBe("/builder/c1");
    expect(chatPath("agent-1", "c1")).toBe("/agents/agent-1/c1");
  });

  it("names Ila even though she isn't in the agents list", () => {
    const agents = [{ agent_id: "agent-1", agent_name: "Support" }];
    expect(agentDisplayName(agents, ILA_AGENT_ID)).toBe("Ila");
    expect(agentDisplayName(agents, "agent-1")).toBe("Support");
    expect(agentDisplayName(agents, "gone")).toBe("Unknown Agent");
  });
});

describe("tool activity", () => {
  it("follows the flag for agents and is never shown for Ila", () => {
    expect(showsToolActivity("agent-1", true)).toBe(true);
    expect(showsToolActivity("agent-1", false)).toBe(false);
    expect(showsToolActivity(ILA_AGENT_ID, true)).toBe(false);
  });
});
