import { describe, expect, it } from "vitest";

import { applyParamPatch } from "./useWorkspaceParams";

describe("applyParamPatch", () => {
  it("sets and removes keys", () => {
    const next = applyParamPatch(new URLSearchParams("step=n1"), { run: "r1", panel: "runs" });
    expect(next?.get("step")).toBe("n1");
    expect(next?.get("run")).toBe("r1");
    expect(next?.get("panel")).toBe("runs");

    const cleared = applyParamPatch(new URLSearchParams("step=n1&run=r1"), { run: null });
    expect(cleared?.has("run")).toBe(false);
    expect(cleared?.get("step")).toBe("n1");
  });

  it("keeps unrelated keys, so two writers cannot discard each other", () => {
    const next = applyParamPatch(new URLSearchParams("step=n1&panel=runs"), { run: "r1" });
    expect(next?.toString()).toBe("step=n1&panel=runs&run=r1");
  });

  /**
   * The guard that stops the navigation loop: selecting a run that is already
   * in the URL must not produce another navigation.
   */
  it("returns null when nothing would change", () => {
    expect(applyParamPatch(new URLSearchParams("run=r1"), { run: "r1" })).toBe(null);
    expect(applyParamPatch(new URLSearchParams(""), { run: null })).toBe(null);
    expect(applyParamPatch(new URLSearchParams("step=n1&run=r1"), { step: "n1", run: "r1" })).toBe(
      null
    );
  });

  it("treats an empty string as a removal", () => {
    const next = applyParamPatch(new URLSearchParams("step=n1"), { step: "" });
    expect(next?.has("step")).toBe(false);
  });

  it("applies several keys in one patch", () => {
    const next = applyParamPatch(new URLSearchParams("focus=trigger"), {
      step: "start-1",
      focus: null,
    });
    expect(next?.get("step")).toBe("start-1");
    expect(next?.has("focus")).toBe(false);
  });
});
