import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createWebPlatform, loginUrl } from "./index";

const values = new Map<string, string>();
beforeEach(() => {
  values.clear();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});
afterEach(() => vi.unstubAllGlobals());

describe("web login URLs", () => {
  it("starts each provider at the API, without a query when there is no invitation", () => {
    expect(loginUrl("google", undefined, "https://api.example.com/")).toBe("https://api.example.com/auth/google");
  });

  it("carries only the invitation's hash context", () => {
    for (const provider of ["google", "cognito"] as const) {
      const url = new URL(loginUrl(provider, "sha256-context", "https://api.example.com/"));
      expect(url.pathname).toBe(`/auth/${provider}`);
      expect([...url.searchParams.entries()]).toEqual([["invitation", "sha256-context"]]);
      expect(url.hash).toBe("");
    }
  });
});

describe("web adapter", () => {
  it("redeems a login code into the auth_token and forgets the last account choice", async () => {
    values.set("active_account_id", "old-account");
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ token: "session-jwt" })));
    vi.stubGlobal("fetch", fetcher);
    const web = createWebPlatform();
    await web.auth.complete("one-use");
    expect(values.get("auth_token")).toBe("session-jwt");
    expect(values.has("active_account_id")).toBe(false);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/auth/session"), expect.objectContaining({
      method: "POST", body: JSON.stringify({ code: "one-use" }),
    }));
  });

  it("refuses a failed redemption without storing anything", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 400 })));
    await expect(createWebPlatform().auth.complete("used")).rejects.toMatchObject({ status: 400 });
    expect(values.has("auth_token")).toBe(false);
  });

  it("has no refresh token: a 401 means signed out", async () => {
    values.set("auth_token", "jwt");
    const web = createWebPlatform();
    expect(web.tokens.accessToken()).toBe("jwt");
    expect(await web.tokens.refresh()).toBeNull();
    await web.auth.end();
    expect(web.tokens.accessToken()).toBeNull();
  });

  it("returns flows to this origin and tolerates blocked storage", () => {
    vi.stubGlobal("window", { location: { origin: "https://innomightlabs.com" } });
    vi.stubGlobal("localStorage", { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } });
    const web = createWebPlatform();
    expect(web.links.returnTo("/dashboard/connectors")).toBe("https://innomightlabs.com/dashboard/connectors");
    expect(web.storage.get("conversations:view")).toBeNull();
    expect(() => web.storage.set("conversations:view", "classic")).not.toThrow();
  });

  it("reports a blocked popup so the caller can offer a link", async () => {
    vi.stubGlobal("window", { open: vi.fn().mockReturnValue(null) });
    expect(await createWebPlatform().links.openAuthPage("https://provider.test", { popup: true })).toBe(false);
  });

  it("sells subscriptions and has no push", () => {
    const web = createWebPlatform();
    expect(web.commerce.canSellSubscriptions).toBe(true);
    expect(web.push).toBeNull();
  });
});
