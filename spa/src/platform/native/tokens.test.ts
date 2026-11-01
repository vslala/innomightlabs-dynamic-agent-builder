import { afterEach, describe, expect, it, vi } from "vitest";
import { createNativeTokens, type Vault } from "./tokens";

/** An owner JWT shape: only the payload's `sub` is read. */
const jwt = (sub: string) => `h.${btoa(JSON.stringify({ sub }))}.s`;

function memoryVault(initial: Record<string, string> = {}): Vault & { values: Map<string, string> } {
  const values = new Map(Object.entries(initial));
  return {
    values,
    get: async (key) => values.get(key) ?? null,
    set: async (key, value) => void values.set(key, value),
    remove: async (key) => void values.delete(key),
  };
}

const stored = (refreshToken = "r1") => ({ session: JSON.stringify({ userId: "u1", refreshToken }) });
const pair = (n: number) => ({ access_token: jwt("u1"), refresh_token: `r${n}`, expires_in: 3600 });

afterEach(() => vi.unstubAllGlobals());

describe("native tokens", () => {
  it("keeps the refresh token and its user in the vault, the access token in memory", async () => {
    const vault = memoryVault();
    const tokens = createNativeTokens(vault, () => "device-1");
    await tokens.save({ accessToken: jwt("u1"), refreshToken: "r1", expiresIn: 3600 });
    expect(tokens.accessToken()).toBe(jwt("u1"));
    expect(JSON.parse(vault.values.get("session")!)).toEqual({ userId: "u1", refreshToken: "r1" });
    expect([...vault.values.values()].join()).not.toContain(jwt("u1"));
  });

  it("needs a refresh at start (no access token) and near expiry, never without a session", async () => {
    const tokens = createNativeTokens(memoryVault(stored()), () => "device-1");
    expect(tokens.needsRefresh()).toBe(false);
    await tokens.load();
    expect(tokens.needsRefresh()).toBe(true);
    await tokens.save({ accessToken: jwt("u1"), expiresIn: 3600 });
    expect(tokens.needsRefresh()).toBe(false);
    expect(tokens.needsRefresh(Date.now() + 56 * 60 * 1000)).toBe(true);
  });

  it("rotates once for concurrent 401s, sending the user, device and refresh token", async () => {
    const vault = memoryVault(stored());
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(pair(2))));
    vi.stubGlobal("fetch", fetcher);
    const tokens = createNativeTokens(vault, () => "device-1");
    await tokens.load();
    const [a, b] = await Promise.all([tokens.refresh(), tokens.refresh()]);
    expect(a).toBe(jwt("u1"));
    expect(b).toBe(a);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ user_id: "u1", device_id: "device-1", refresh_token: "r1" });
    expect(JSON.parse(vault.values.get("session")!).refreshToken).toBe("r2");
  });

  it("signs out when the API refuses the refresh token", async () => {
    const vault = memoryVault(stored());
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "invalid_grant" }), { status: 401 })));
    const tokens = createNativeTokens(vault, () => "device-1");
    await tokens.load();
    expect(await tokens.refresh()).toBeNull();
    expect(vault.values.has("session")).toBe(false);
    expect(tokens.needsRefresh()).toBe(false);
  });

  it("stays signed in when offline, to try again later", async () => {
    const vault = memoryVault(stored());
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const tokens = createNativeTokens(vault, () => "device-1");
    await tokens.load();
    expect(await tokens.refresh()).toBeNull();
    expect(vault.values.has("session")).toBe(true);
  });

  it("revokes with proof of the refresh token, and ignores a failed revoke", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetcher);
    const tokens = createNativeTokens(memoryVault(stored("r9")), () => "device-1");
    await tokens.load();
    await expect(tokens.revoke()).resolves.toBeUndefined();
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({ user_id: "u1", device_id: "device-1", refresh_token: "r9" });
  });
});
