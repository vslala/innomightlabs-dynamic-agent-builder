import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { redeemLoginSession } from "./loginHandoff";
import { PENDING_INVITATION_KEY } from "./continuation";

const values = new Map<string, string>();
beforeEach(() => {
  values.clear();
  values.set("active_account_id", "old-account");
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ token: "session-jwt" }))));
});
afterEach(() => vi.unstubAllGlobals());

describe("login-success handoff", () => {
  it("redeems the code and hands invitation navigation precedence over checkout/dashboard", async () => {
    const pending = new Map([[PENDING_INVITATION_KEY, "secret"], ["pendingCheckout", "checkout"]]);
    vi.stubGlobal("sessionStorage", { getItem: (key: string) => pending.get(key), removeItem: vi.fn() });
    const navigate = vi.fn();
    const tokenForNormalContinuation = await redeemLoginSession("one-use", true, navigate);
    expect(tokenForNormalContinuation).toBeNull();
    expect(navigate).toHaveBeenCalledExactlyOnceWith("/invitations/accept", { replace: true });
    expect(values.get("auth_token")).toBe("session-jwt");
    expect(values.has("active_account_id")).toBe(false);
    expect(pending.get(PENDING_INVITATION_KEY)).toBe("secret");
    expect(pending.get("pendingCheckout")).toBe("checkout");
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/auth/session"), expect.objectContaining({ method: "POST", body: JSON.stringify({ code: "one-use" }), headers: { "Content-Type": "application/json" } }));
  });
  it("returns the session token unchanged for normal checkout/dashboard continuation", async () => {
    const navigate = vi.fn();
    expect(await redeemLoginSession("one-use", false, navigate)).toBe("session-jwt");
    expect(navigate).not.toHaveBeenCalled();
  });
});
