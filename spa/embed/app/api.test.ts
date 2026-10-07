import { afterEach, describe, expect, it, vi } from "vitest";
import { GuestEntryError, GuestSessionEndedError, SignedOutError, WidgetApi } from "./api";

const tokenBody = { access_token: "token", refresh_token: "refresh", visitor: { visitor_id: "visitor", email: "guest@example.com", kind: "guest" } };
function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function mockFetch(body: unknown, status = 200) {
  const fetcher = vi.fn().mockResolvedValue(response(body, status));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
afterEach(() => vi.unstubAllGlobals());

describe("guest API", () => {
  it("starts with only the key and email and maps guest identity", async () => {
    const fetcher = mockFetch(tokenBody);
    const session = await WidgetApi.startGuest("pk_test", "guest@example.com");
    expect(session.visitor.kind).toBe("guest");
    expect(session.refreshToken).toBe("refresh");
    expect(fetcher).toHaveBeenCalledWith("/widget/auth/guest", expect.objectContaining({
      method: "POST", body: JSON.stringify({ email: "guest@example.com" }),
      headers: { "Content-Type": "application/json", "X-API-Key": "pk_test" },
    }));
  });
  it("defaults legacy Google token responses to Google", async () => {
    mockFetch({ ...tokenBody, visitor: { visitor_id: "google", email: "g@example.com" } });
    expect((await WidgetApi.redeem("pk", "code")).visitor.kind).toBe("google");
  });
  it("preserves guest kind during refresh", async () => {
    mockFetch(tokenBody);
    expect((await WidgetApi.refresh("pk", "refresh")).visitor.kind).toBe("guest");
  });
  it("shows the exact 422 validation reason", async () => {
    mockFetch({ detail: "The domain name asdf.asdf does not exist." }, 422);
    await expect(WidgetApi.startGuest("pk", "a@asdf.asdf")).rejects.toThrow("The domain name asdf.asdf does not exist.");
  });
  it("offers Google rather than exposing a rate-limit code", async () => {
    mockFetch({ detail: "guest_start_limited" }, 429);
    await expect(WidgetApi.startGuest("pk", "a@example.com")).rejects.toThrow("continue with Google");
  });
  it.each([422, 503, 504])("offers retry on an email lookup timeout (%i)", async (status) => {
    mockFetch({ detail: "Email lookup timed out" }, status);
    await expect(WidgetApi.startGuest("pk", "a@example.com")).rejects.toMatchObject({
      message: "We couldn't check that address. Please try again.", retryable: true,
    });
  });
  it("handles disabled guest access without signing anyone out", async () => {
    mockFetch({ detail: "guests_disabled" }, 404);
    await expect(WidgetApi.startGuest("pk", "a@example.com")).rejects.toBeInstanceOf(GuestEntryError);
  });
  it("ends a guest via authenticated POST and accepts an empty 204", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    const api = new WidgetApi("pk", async () => "token");
    await expect(api.endGuest()).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledWith("/widget/auth/guest/end", expect.objectContaining({
      method: "POST", headers: expect.objectContaining({ Authorization: "Bearer token", "X-API-Key": "pk" }),
    }));
  });
  it("distinguishes guest expiration on requests and refresh", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => response({ detail: "guest_session_ended" }, 401)));
    const api = new WidgetApi("pk", async () => "token");
    await expect(api.listConversations()).rejects.toBeInstanceOf(GuestSessionEndedError);
    await expect(api.endGuest()).rejects.toBeInstanceOf(GuestSessionEndedError);
    await expect(WidgetApi.refresh("pk", "refresh")).rejects.toBeInstanceOf(GuestSessionEndedError);
  });
  it("keeps ordinary Google expiry separate", async () => {
    mockFetch({ detail: "expired" }, 401);
    const api = new WidgetApi("pk", async () => "token");
    const error = await api.listConversations().catch((err: unknown) => err);
    expect(error).toBeInstanceOf(SignedOutError);
    expect(error).not.toBeInstanceOf(GuestSessionEndedError);
  });
  it("gives a friendly message-limit response", async () => {
    mockFetch({ detail: "guest_message_limited" }, 429);
    const api = new WidgetApi("pk", async () => "token");
    await expect(api.createConversation("Hi")).rejects.toThrow("continue with Google");
  });
});
