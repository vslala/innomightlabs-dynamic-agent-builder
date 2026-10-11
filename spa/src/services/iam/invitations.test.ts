import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { InvitationError, invitationErrorMessage, invitationService } from "./invitations";
import { HttpError } from "../http/client";

beforeEach(() => {
  const values = new Map([["auth_token", "jwt"], ["active_account_id", "account-1"]]);
  vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  vi.stubGlobal("window", { dispatchEvent: vi.fn() });
  vi.stubGlobal("CustomEvent", class {
    type: string;
    detail: unknown;
    constructor(type: string, options: { detail: unknown }) { this.type = type; this.detail = options.detail; }
  });
});
afterEach(() => vi.unstubAllGlobals());
function respond(body: unknown, status = 200) {
  const fetcher = vi.fn().mockResolvedValue(status === 204 ? new Response(null, { status }) : new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("invitation HTTP boundary", () => {
  it("previews with a POST body and no identity/account headers or URL token", async () => {
    const fetcher = respond({ account_name: "Workspace" });
    const signal = new AbortController().signal;
    await invitationService.preview("raw-secret", signal);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(expect.stringMatching(/\/invitations\/preview$/), {
      method: "POST", signal, body: JSON.stringify({ token: "raw-secret" }), headers: { "Content-Type": "application/json" },
    });
  });

  it.each([
    ["list", "GET", "/iam/invitations", undefined],
    ["create", "POST", "/iam/invitations", JSON.stringify({ email: "invite@example.com" })],
    ["resend", "POST", "/iam/invitations/id/resend", undefined],
    ["revoke", "DELETE", "/iam/invitations/id", undefined],
    ["accept", "POST", "/invitations/accept", JSON.stringify({ token: "raw-secret" })],
  ] as const)("%s uses the real method and shared authenticated headers", async (operation, method, path, body) => {
    const fetcher = respond({}, operation === "revoke" ? 204 : 200);
    switch (operation) {
      case "list": await invitationService.list(); break;
      case "create": await invitationService.create("invite@example.com"); break;
      case "resend": await invitationService.resend("id"); break;
      case "revoke": await invitationService.revoke("id"); break;
      case "accept": await invitationService.accept("raw-secret"); break;
    }
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(expect.stringContaining(path), expect.objectContaining({
      method, ...(body ? { body } : {}), headers: { "Content-Type": "application/json", Authorization: "Bearer jwt", "X-Account-Id": "account-1" },
    }));
    expect(fetcher.mock.calls[0][0]).not.toContain("raw-secret");
    expect(fetcher.mock.calls[0][0]).not.toContain("?");
  });

  it.each(["list", "create", "resend", "revoke", "preview"] as const)("%s retains default 401 redirection", async (operation) => {
    const location = { pathname: "/invitations/accept", href: "/invitations/accept" };
    vi.stubGlobal("window", { location });
    respond({}, 401);
    let request: Promise<unknown>;
    switch (operation) {
      case "list": request = invitationService.list(); break;
      case "create": request = invitationService.create("a@example.com"); break;
      case "resend": request = invitationService.resend("id"); break;
      case "revoke": request = invitationService.revoke("id"); break;
      case "preview": request = invitationService.preview("pending-secret"); break;
    }
    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe("/");
    expect(localStorage.getItem("auth_token")).toBeNull();
  });

  it("preserves persisted invite IDs on delivery failure without reporting success", async () => {
    respond({ detail: { code: "MAIL_DELIVERY_FAILED", message: "Email delivery failed; resend the invitation.", invite_id: "saved-id" } }, 502);
    await expect(invitationService.create("a@example.com")).rejects.toMatchObject({ status: 502, detail: { invite_id: "saved-id" }, message: "Email delivery failed; resend the invitation." });
  });

  it.each(["SEAT_LIMIT_UNAVAILABLE", "SEAT_LIMIT_REACHED"])("provides actionable %s errors", async (code) => {
    respond({ detail: { code, message: "Seats blocked." } }, 409);
    try { await invitationService.create("a@example.com"); throw new Error("unexpected success"); }
    catch (error) {
      expect(error).toBeInstanceOf(InvitationError);
      expect(invitationErrorMessage(error)).toContain("administrator");
      expect(invitationErrorMessage(error)).toContain("Seats blocked.");
    }
  });

  it("narrows structured detail fields instead of trusting unknown values", async () => {
    respond({ detail: { code: 42, message: { invalid: true }, invite_id: ["wrong-type"] }, message: "Readable fallback" }, 502);
    await expect(invitationService.create("a@example.com")).rejects.toMatchObject({
      status: 502, message: "Readable fallback", detail: { message: "Readable fallback" },
    });
  });

  it("leaves unstructured shared errors unchanged", async () => {
    respond({ detail: "Forbidden" }, 403);
    await expect(invitationService.list()).rejects.toEqual(new HttpError(403, "Forbidden", "Forbidden"));
  });

  it.each([409, 429])("shows API pending-cap/rate-limit messages (%s)", async (status) => {
    respond({ detail: { code: "LIMIT", message: "Wait before sending another invitation." } }, status);
    await expect(invitationService.create("a@example.com")).rejects.toThrow("Wait before sending another invitation.");
  });
});
