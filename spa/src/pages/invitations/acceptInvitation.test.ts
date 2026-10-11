import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { invitationService } from "../../services/iam/invitations";
import { accountService } from "../../services/accounts";
import { acceptInvitation } from "./acceptInvitation";
import { PENDING_INVITATION_KEY } from "./continuation";
import { HttpError } from "../../services/http";

const values = new Map<string, string>();
const pending = new Map<string, string>();
const removePending = vi.fn((key: string) => pending.delete(key));
beforeEach(() => {
  values.clear();
  values.set("active_account_id", "previous-account");
  removePending.mockClear();
  pending.clear();
  pending.set(PENDING_INVITATION_KEY, "pending-secret");
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  vi.stubGlobal("sessionStorage", { getItem: (key: string) => pending.get(key) ?? null, removeItem: removePending });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("explicit acceptance handoff", () => {
  it("keeps the old local account until server selection succeeds, then clears the pending token", async () => {
    vi.spyOn(invitationService, "accept").mockResolvedValue({ account_id: "joined", invite_id: "i" });
    let finish!: (response: Response) => void;
    const fetcher = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
    vi.stubGlobal("fetch", fetcher);
    const switchAccount = vi.spyOn(accountService, "switchTo");
    const result = acceptInvitation("secret");
    await vi.waitFor(() => expect(fetcher).toHaveBeenCalledOnce());
    expect(switchAccount).toHaveBeenCalledExactlyOnceWith("joined", { redirectOnAuthError: false });
    expect(values.get("active_account_id")).toBe("previous-account");
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/accounts/active"), expect.objectContaining({
      method: "PUT", body: JSON.stringify({ account_id: "joined" }),
      headers: expect.objectContaining({ "X-Account-Id": "previous-account" }),
    }));
    expect(removePending).not.toHaveBeenCalled();
    finish(new Response(JSON.stringify({ account_id: "joined" })));
    await result;
    expect(values.get("active_account_id")).toBe("joined");
    expect(removePending).toHaveBeenCalledExactlyOnceWith(PENDING_INVITATION_KEY);
  });
  it("keeps continuation on rejected identity or seat/expiry errors", async () => {
    vi.spyOn(invitationService, "accept").mockRejectedValue(new Error("Sign in with the invited email"));
    const switchAccount = vi.spyOn(accountService, "switchTo");
    await expect(acceptInvitation("secret")).rejects.toThrow("invited email");
    expect(switchAccount).not.toHaveBeenCalled();
    expect(values.get("active_account_id")).toBe("previous-account");
    expect(removePending).not.toHaveBeenCalled();
  });
  it("acceptance 401 clears auth and stays on the invitation page with its pending token", async () => {
    values.set("auth_token", "test-token");
    const location = { pathname: "/invitations/accept", href: "/invitations/accept" };
    vi.stubGlobal("window", { location });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    const switchAccount = vi.spyOn(accountService, "switchTo");
    await expect(acceptInvitation("pending-secret")).rejects.toBeInstanceOf(HttpError);
    expect(values.has("auth_token")).toBe(false);
    expect(values.get("active_account_id")).toBe("previous-account");
    expect(location.href).toBe("/invitations/accept");
    expect(pending.get(PENDING_INVITATION_KEY)).toBe("pending-secret");
    expect(removePending).not.toHaveBeenCalled();
    expect(switchAccount).not.toHaveBeenCalled();
  });

  it("account-switch 401 keeps the invitation page, old account and pending token",  async () => {
    values.set("auth_token", "test-token");
    const location = { pathname: "/invitations/accept", href: "/invitations/accept" };
    vi.stubGlobal("window", { location });
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ account_id: "joined", invite_id: "i" })))
      .mockResolvedValueOnce(new Response(null, { status: 401 })));
    await expect(acceptInvitation("pending-secret")).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe("/invitations/accept");
    expect(values.has("auth_token")).toBe(false);
    expect(values.get("active_account_id")).toBe("previous-account");
    expect(pending.get(PENDING_INVITATION_KEY)).toBe("pending-secret");
    expect(removePending).not.toHaveBeenCalled();
  });

  it("keeps the token if membership succeeded but server account switching failed", async () => {
    vi.spyOn(invitationService, "accept").mockResolvedValue({ account_id: "joined", invite_id: "i" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(acceptInvitation("secret")).rejects.toThrow("Network error");
    expect(values.get("active_account_id")).toBe("previous-account");
    expect(pending.get(PENDING_INVITATION_KEY)).toBe("pending-secret");
    expect(removePending).not.toHaveBeenCalled();
  });
});
