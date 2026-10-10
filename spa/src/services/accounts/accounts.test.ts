import { afterEach, describe, expect, it, vi } from "vitest";
import { authHeaders } from "../http";
import { accountService, type AccountMembership } from ".";

afterEach(() => vi.unstubAllGlobals());

function storage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  return values;
}

const membership = (account_id: string, active = false): AccountMembership => ({
  account_id, name: account_id, access_summary: "member", membership_status: "active", joined_at: "", active,
});

describe("the account a tab acts in", () => {
  it("is the tab's own choice while it is still one of the person's accounts", () => {
    storage({ active_account_id: "b" });
    expect(accountService.current([membership("a", true), membership("b")])?.account_id).toBe("b");
  });

  it("falls back to the one the API picks when the tab's choice is gone", () => {
    storage({ active_account_id: "left-since" });
    expect(accountService.current([membership("a"), membership("b", true)])?.account_id).toBe("b");
  });

  it("is named on every request, next to the token", () => {
    storage({ auth_token: "t", active_account_id: "a" });
    expect(authHeaders()).toEqual({ Authorization: "Bearer t", "X-Account-Id": "a" });
  });

  it("is remembered by the API and the tab when switched", async () => {
    const values = storage({ auth_token: "t" });
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(membership("b", true)), { status: 200 }));
    vi.stubGlobal("fetch", fetcher);

    await accountService.switchTo("b");

    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/accounts/active"), expect.objectContaining({
      method: "PUT", body: JSON.stringify({ account_id: "b" }),
    }));
    expect(values.get("active_account_id")).toBe("b");
  });
});
