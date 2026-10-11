import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { httpClient, HttpError } from "./client";

const values = new Map<string, string>();
const location = { pathname: "/invitations/accept", href: "/invitations/accept" };
const dispatchEvent = vi.fn();
beforeEach(() => {
  values.clear();
  values.set("auth_token", "test-token");
  values.set("active_account_id", "account-1");
  location.pathname = "/invitations/accept";
  location.href = "/invitations/accept";
  dispatchEvent.mockClear();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  vi.stubGlobal("window", { location, dispatchEvent });
  vi.stubGlobal("CustomEvent", class {
    type: string;
    detail: unknown;
    constructor(type: string, options: { detail: unknown }) {
      this.type = type;
      this.detail = options.detail;
    }
  });
});
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function respond(body: unknown, status = 200, headers?: HeadersInit) {
  const fetcher = vi.fn().mockResolvedValue(new Response(status === 204 ? null : JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("shared HTTP error detail", () => {
  it("preserves structured detail and selects its readable message", async () => {
    const detail = { code: "MAIL_DELIVERY_FAILED", message: "Resend the invitation.", invite_id: "persisted" };
    respond({ detail }, 502);
    await expect(httpClient.post("/iam/invitations", { email: "a@example.com" })).rejects.toMatchObject({
      name: "HttpError", status: 502, message: detail.message, detail,
    });
  });

  it.each([
    [{ detail: "Forbidden" }, "Forbidden", "Forbidden"],
    [{ detail: { code: "LIMIT" }, message: "Limit reached" }, "Limit reached", { code: "LIMIT" }],
    [{ detail: { message: 42 } }, "Request failed", { message: 42 }],
    [{ detail: [{ msg: "Invalid email" }] }, "Request failed", [{ msg: "Invalid email" }]],
    [{ detail: null }, "Request failed", null],
    [{ detail: 42 }, "Request failed", 42],
    [{ message: "Unavailable" }, "Unavailable", undefined],
    [{ message: { unsafe: "object" } }, "Request failed", undefined],
    [null, "Request failed", undefined],
    [{ detail: { message: "" } }, "", { message: "" }],
  ])("narrows malformed or legacy response %# to a safe string", async (body, message, detail) => {
    respond(body, 400);
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 400, message, detail });
  });

  it("falls back safely for non-JSON error responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("upstream failure", { status: 502 })));
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 502, message: "Request failed", detail: undefined });
  });

  it("keeps the two-argument HttpError constructor compatible", () => {
    const error = new HttpError(0, "offline");
    expect(error.message).toBe("offline");
    expect(error.detail).toBeUndefined();
  });
});

describe("shared HTTP interceptors", () => {
  it("attaches identity/account headers and preserves request cancellation", async () => {
    const fetcher = respond({ ok: true });
    const signal = new AbortController().signal;
    await httpClient.get("/test", { signal });
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/test"), {
      method: "GET", signal, headers: { "Content-Type": "application/json", Authorization: "Bearer test-token", "X-Account-Id": "account-1" },
    });
  });

  it("skipAuth omits identity/account headers but still processes refresh before errors", async () => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    const fetcher = respond({ detail: { message: "Try later" } }, 503, { "x-refreshed-token": "refreshed-test-token" });
    await expect(httpClient.post("/test", {}, { skipAuth: true })).rejects.toMatchObject({ status: 503, message: "Try later" });
    expect(values.get("auth_token")).toBe("refreshed-test-token");
    expect(fetcher.mock.calls[0][1].headers).toEqual({ "Content-Type": "application/json" });
  });

  it("401 removes only auth, redirects home, and leaves invitation continuation intact", async () => {
    vi.spyOn(console, "log").mockImplementation(() => {});
    const pending = new Map([["pendingInvitationToken", "pending-secret"]]);
    vi.stubGlobal("sessionStorage", { getItem: (key: string) => pending.get(key) });
    respond({ detail: { message: "Expired" } }, 401, { "x-refreshed-token": "refreshed-test-token" });
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 401, message: "Unauthorized - Please login again" });
    expect(values.has("auth_token")).toBe(false);
    expect(values.get("active_account_id")).toBe("account-1");
    expect(location.href).toBe("/");
    expect(pending.get("pendingInvitationToken")).toBe("pending-secret");
  });

  it("401 opt-out clears auth without redirecting or removing invitation continuation", async () => {
    const pending = new Map([["pendingInvitationToken", "pending-secret"]]);
    vi.stubGlobal("sessionStorage", { getItem: (key: string) => pending.get(key) });
    const fetcher = respond({}, 401);
    await expect(httpClient.post("/test", {}, { redirectOnAuthError: false })).rejects.toMatchObject({ status: 401 });
    expect(values.has("auth_token")).toBe(false);
    expect(values.get("active_account_id")).toBe("account-1");
    expect(location.href).toBe("/invitations/accept");
    expect(pending.get("pendingInvitationToken")).toBe("pending-secret");
    expect(fetcher.mock.calls[0][1]).not.toHaveProperty("redirectOnAuthError");
  });

  it("401 does not redirect when already home", async () => {
    location.pathname = "/";
    location.href = "/?retained=1";
    respond({}, 401);
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 401 });
    expect(location.href).toBe("/?retained=1");
  });

  it("429 dispatches the existing rate-limit event and preserves the API error", async () => {
    const detail = { code: "RATE_LIMIT", message: "Please wait", upgrade_url: "/pricing" };
    respond({ detail }, 429);
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 429, message: "Please wait", detail });
    expect(dispatchEvent).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ type: "rate-limit", detail: { message: "Please wait", upgradeUrl: "/pricing" } }));
  });

  it("does not dispatch malformed rate-limit messages", async () => {
    respond({ detail: { message: { invalid: true } } }, 429);
    await expect(httpClient.get("/test")).rejects.toMatchObject({ status: 429, message: "Request failed" });
    expect(dispatchEvent).not.toHaveBeenCalled();
  });

  it("preserves network failure behavior", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(httpClient.get("/test")).rejects.toEqual(new HttpError(0, "Network error - please check your connection"));
  });

  it("keeps multipart content type browser-owned", async () => {
    const fetcher = respond({ ok: true });
    const body = new FormData();
    await httpClient.postForm("/test", body);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: "POST", body, headers: { Authorization: "Bearer test-token", "X-Account-Id": "account-1" } });
    expect(fetcher.mock.calls[0][1].headers).not.toHaveProperty("Content-Type");
  });

  it("keeps the shared 204 empty-object behavior", async () => {
    respond(undefined, 204);
    expect(await httpClient.delete("/test")).toEqual({});
  });
});
