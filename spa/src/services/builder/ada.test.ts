import { describe, expect, it } from "vitest";
import { ADA_AGENT_ID, agentDisplayName, chatPath, showsToolActivity } from "./ada";

describe("Ada's chat routes", () => {
  it("sends Ada's conversations to the builder and everyone else's to their agent", () => {
    expect(chatPath(ADA_AGENT_ID, "c1")).toBe("/builder/c1");
    expect(chatPath("agent-1", "c1")).toBe("/agents/agent-1/c1");
  });

  it("names Ada even though she isn't in the agents list", () => {
    const agents = [{ agent_id: "agent-1", agent_name: "Support" }];
    expect(agentDisplayName(agents, ADA_AGENT_ID)).toBe("Ada");
    expect(agentDisplayName(agents, "agent-1")).toBe("Support");
    expect(agentDisplayName(agents, "gone")).toBe("Unknown Agent");
  });
});

describe("tool activity", () => {
  it("follows the flag for agents and is never shown for Ada", () => {
    expect(showsToolActivity("agent-1", true)).toBe(true);
    expect(showsToolActivity("agent-1", false)).toBe(false);
    expect(showsToolActivity(ADA_AGENT_ID, true)).toBe(false);
  });
});
