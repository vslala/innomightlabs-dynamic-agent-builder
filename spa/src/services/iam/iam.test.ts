import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "../http/client";
import { iamService } from ".";

const capabilities = { can_list_members: true, can_invite: false };
const member = {
  user_id: "member-1", email: "member@example.com", name: "Member", status: "active",
  joined_at: "2026-10-01", is_owner: false, group_ids: ["group-1"], policies: ["Viewer"],
};

beforeEach(() => {
  const values = new Map([ ["auth_token", "test-token"], ["active_account_id", "account-1"] ]);
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
});
afterEach(() => vi.unstubAllGlobals());

function respond(body: unknown, status = 200) {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

describe("IAM shared HTTP boundary", () => {
  it("requests capabilities with authentication, account and cancellation headers/options", async () => {
    const fetcher = respond(capabilities);
    const signal = new AbortController().signal;
    expect(await iamService.getCapabilities(signal)).toEqual(capabilities);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/iam/capabilities"), {
      method: "GET", signal,
      headers: { "Content-Type": "application/json", Authorization: "Bearer test-token", "X-Account-Id": "account-1" },
    });
  });

  it("returns the member array including string group IDs and policies", async () => {
    const fetcher = respond([member]);
    const signal = new AbortController().signal;
    expect(await iamService.listMembers(signal)).toEqual([member]);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/iam/members"), expect.objectContaining({
      method: "GET", signal,
      headers: expect.objectContaining({ Authorization: "Bearer test-token", "X-Account-Id": "account-1" }),
    }));
  });

  it("propagates forbidden responses rather than returning an empty list", async () => {
    respond({ detail: "Missing iam:ListMembers" }, 403);
    await expect(iamService.listMembers()).rejects.toMatchObject({
      name: "HttpError", status: 403, message: "Missing iam:ListMembers",
    });
  });

  it("propagates capability endpoint failures", async () => {
    respond({ detail: "Service unavailable" }, 503);
    await expect(iamService.getCapabilities()).rejects.toMatchObject({ status: 503, message: "Service unavailable" });
  });

  it("uses the shared network error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(iamService.getCapabilities()).rejects.toEqual(new HttpError(0, "Network error - please check your connection"));
  });
});
