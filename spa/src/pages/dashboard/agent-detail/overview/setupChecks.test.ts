import { describe, expect, it } from "vitest";

import { setupChecks, type SetupFacts } from "./setupChecks";

const fresh: SetupFacts = {
  configured: true,
  hasActiveApiKey: false,
  a2aEnabled: false,
  activeSkills: 0,
  linkedKnowledgeBases: 0,
};

describe("setupChecks", () => {
  it("lists every check in a fixed order", () => {
    expect(setupChecks(fresh).map((check) => check.key)).toEqual(["configured", "api-key", "skills", "knowledge", "a2a"]);
  });

  it("says why A2A can't be enabled without an API key, and unblocks it once there is one", () => {
    const a2a = (facts: SetupFacts) => setupChecks(facts).find((check) => check.key === "a2a");

    expect(a2a(fresh)?.blockedBy).toBe("Needs an API key first");
    expect(a2a({ ...fresh, hasActiveApiKey: true })?.blockedBy).toBeNull();
  });

  it("marks checks done from the facts and counts what's in place", () => {
    const checks = setupChecks({ ...fresh, hasActiveApiKey: true, a2aEnabled: true, activeSkills: 5, linkedKnowledgeBases: 2 });

    expect(checks.every((check) => check.done)).toBe(true);
    expect(checks.find((check) => check.key === "skills")?.hint).toBe("5 active");
    expect(checks.find((check) => check.key === "knowledge")?.hint).toBe("2 linked");
  });
});
