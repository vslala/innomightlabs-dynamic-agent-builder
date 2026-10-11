import { describe, expect, it, vi } from "vitest";
import { captureInvitationToken, invitationLoginUrl, isInvitationContinuation, PENDING_INVITATION_KEY } from "./continuation";

function browser() {
  const location = { pathname: "/invitations/accept", search: "", hash: "#token=secret%2Btoken" };
  const values = new Map<string, string>();
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: vi.fn((key: string, value: string) => { expect(location.hash).toBe(""); values.set(key, value); }) };
  const history = { state: { retained: true }, replaceState: vi.fn((_state: unknown, _unused: string, url: string | URL | null) => { const cleaned = new URL(String(url), "https://innomightlabs.com"); location.hash = cleaned.hash; location.search = cleaned.search; }) };
  return { location, values, storage, history };
}

describe("invitation continuation", () => {
  it("cleans the fragment before storage or fetch and survives StrictMode's repeated bootstrap", () => {
    const { location, values, storage, history } = browser();
    expect(captureInvitationToken(location, history, storage)).toEqual({ token: "secret+token" });
    expect(captureInvitationToken(location, history, storage)).toEqual({ token: "secret+token" });
    expect(history.replaceState).toHaveBeenCalledOnce();
    expect(storage.setItem).toHaveBeenCalledExactlyOnceWith(PENDING_INVITATION_KEY, "secret+token");
    expect([...values.keys()]).toEqual([PENDING_INVITATION_KEY]);
  });
  it("removes the secret even if storage access itself throws", () => {
    const { location, history } = browser();
    const result = captureInvitationToken(location, history, () => { throw new Error("blocked"); });
    expect(location.hash).toBe("");
    expect(result.token).toBeNull();
    expect(result.error).toContain("session storage");
    expect(JSON.stringify(result)).not.toContain("secret+token");
  });
  it("fails closed on a storage write error without leaking the token", () => {
    const { location, history } = browser();
    const result = captureInvitationToken(location, history, { getItem: () => null, setItem: () => { throw new Error("quota"); } });
    expect(location.hash).toBe("");
    expect(result.token).toBeNull();
    expect(result.error).toBeTruthy();
  });
  it("never falls back to an old stored token after a storage-error marker", () => {
    const { location, history, storage, values } = browser();
    values.set(PENDING_INVITATION_KEY, "old-token");
    location.search = "?invitation_storage_error=1";
    const read = vi.spyOn(storage, "getItem");
    const result = captureInvitationToken(location, history, storage);
    expect(result.token).toBeNull();
    expect(result.error).toContain("reopen the invitation link");
    expect(read).not.toHaveBeenCalled();
    expect(storage.setItem).not.toHaveBeenCalled();
    expect(location.hash).toBe("");
  });

  it("links directly to both providers with only the preview hash context", () => {
    for (const provider of ["google", "cognito"] as const) {
      const url = new URL(invitationLoginUrl(provider, "sha256-context", "https://api.example.com/"));
      expect(url.pathname).toBe(`/auth/${provider}`);
      expect([...url.searchParams.entries()]).toEqual([["invitation", "sha256-context"]]);
      expect(url.hash).toBe("");
      expect(url.href).not.toContain("secret+token");
    }
  });
  it("captures the one-use callback invitation marker independently of checkout", () => {
    expect(isInvitationContinuation(new URLSearchParams("code=one-use&invitation=1"))).toBe(true);
    expect(isInvitationContinuation(new URLSearchParams("code=one-use"))).toBe(false);
    expect(isInvitationContinuation(new URLSearchParams("invitation=0"))).toBe(false);
  });
});
