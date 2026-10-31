import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { savePendingCheckout, takePendingCheckout } from "./pendingCheckout";

const values = new Map<string, string>();
beforeEach(() => {
  values.clear();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("pending checkout", () => {
  it("resumes a checkout saved before sign-in, once", () => {
    savePendingCheckout("pro", "monthly", 1_000);
    expect(takePendingCheckout(1_000 + 60_000)).toEqual({ planKey: "pro", billingCycle: "monthly", timestamp: 1_000 });
    expect(takePendingCheckout(1_000 + 60_000)).toBeNull();
  });

  it("drops a checkout older than ten minutes", () => {
    savePendingCheckout("pro", "yearly", 0);
    expect(takePendingCheckout(10 * 60 * 1000)).toBeNull();
    expect(values.size).toBe(0);
  });

  it("drops what the old Pricing page wrote without a timestamp, and anything unreadable", () => {
    values.set("pendingCheckout", JSON.stringify({ planKey: "pro", billingCycle: "monthly" }));
    expect(takePendingCheckout()).toBeNull();
    values.set("pendingCheckout", "{not json");
    expect(takePendingCheckout()).toBeNull();
  });
});
