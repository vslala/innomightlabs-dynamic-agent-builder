import { afterEach, describe, expect, it, vi } from "vitest";
import { loadView, parseView, saveView } from "./conversationView";

afterEach(() => vi.unstubAllGlobals());

describe("the saved conversations view", () => {
  it("is the cloud unless classic was chosen", () => {
    expect(parseView(null)).toBe("cloud");
    expect(parseView("cloud")).toBe("cloud");
    expect(parseView("classic")).toBe("classic");
    expect(parseView("grid")).toBe("cloud");
  });

  it("is remembered between visits", () => {
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
    expect(loadView()).toBe("cloud");
    saveView("classic");
    expect(loadView()).toBe("classic");
    saveView("cloud");
    expect(loadView()).toBe("cloud");
  });

  it("still works when storage is blocked", () => {
    const blocked = () => {
      throw new Error("denied");
    };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked });
    expect(loadView()).toBe("cloud");
    expect(() => saveView("classic")).not.toThrow();
  });
});
