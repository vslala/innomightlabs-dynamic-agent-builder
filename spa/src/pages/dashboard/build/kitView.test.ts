import { describe, expect, it } from "vitest";

import type { KitPlan, KitSummary, KitVersion } from "../../../services/kits/KitApiService";
import { canRollBackTo, changingSteps, kitContents, kitStatus, versionLabel } from "./kitView";

const kit: KitSummary = {
  kit_id: "k1",
  title: "Website support agent",
  status: "active",
  current_version: 3,
  versions: 3,
  counts: { WidgetKey: 1, KnowledgeBase: 1, Agent: 2 },
  created_at: "2026-10-10T09:00:00Z",
};

function version(overrides: Partial<KitVersion>): KitVersion {
  return {
    version: 2,
    deployment_id: "d2",
    action: "apply",
    status: "applied",
    current: false,
    steps: [],
    removed: [],
    created_at: "2026-10-10T09:00:00Z",
    ...overrides,
  };
}

describe("kitContents", () => {
  it("lists what people chat with first, one and many", () => {
    expect(kitContents(kit.counts)).toBe("2 agents · 1 knowledge base · 1 chat widget");
    expect(kitContents({ McpConnection: 1, Unknown: 2 })).toBe("1 tool connection · 2 Unknown");
    expect(kitContents({})).toBe("Nothing in it");
  });
});

describe("kitStatus", () => {
  it("shows the version, or that it's gone", () => {
    expect(kitStatus(kit)).toEqual({ status: "active", label: "v3" });
    expect(kitStatus({ ...kit, status: "removed" }).label).toBe("Removed");
  });
});

describe("versions", () => {
  it("say what each did", () => {
    expect(versionLabel(version({ version: 1 }))).toBe("Built");
    expect(versionLabel(version({}))).toBe("Changed");
    expect(versionLabel(version({ action: "rollback", rolled_back_to: 1 }))).toBe("Rolled back to v1");
    expect(versionLabel(version({ action: "remove" }))).toBe("Removed everything");
  });

  it("can be gone back to only if they finished and aren't current or a removal", () => {
    expect(canRollBackTo(version({}), kit)).toBe(true);
    expect(canRollBackTo(version({ current: true }), kit)).toBe(false);
    expect(canRollBackTo(version({ status: "failed_partial" }), kit)).toBe(false);
    expect(canRollBackTo(version({ action: "remove" }), kit)).toBe(false);
    expect(canRollBackTo(version({}), { ...kit, status: "removed" })).toBe(false);
  });
});

describe("changingSteps", () => {
  it("hides what's kept as it is, unless it was edited outside the kit", () => {
    const step = { kind: "Agent", summary: "", changes: [], removals: [], drift: [] };
    const plan: KitPlan = {
      ok: true,
      steps: [
        { ...step, resource: "kept", action: "unchanged" },
        { ...step, resource: "edited", action: "unchanged", drift: ["instructions was changed outside the blueprint"] },
        { ...step, resource: "gone", action: "remove" },
      ],
      blockers: [],
      removals: [],
    };
    expect(changingSteps(plan).map((s) => s.resource)).toEqual(["edited", "gone"]);
  });
});
