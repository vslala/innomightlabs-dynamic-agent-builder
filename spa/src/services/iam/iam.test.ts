import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "../http/client";
import { iamService } from ".";

const capabilities = { can_list_members: true, can_invite: false };
const member = {
  user_id: "member-1", email: "member@example.com", name: "Member", status: "active",
  joined_at: "2026-10-01", is_owner: false, group_ids: ["group-1"], policies: [{ policy: "ViewOnlyAccess", name: "ViewOnlyAccess" }],
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

  it("returns the member array including group IDs and named policies", async () => {
    const fetcher = respond([member]);
    const signal = new AbortController().signal;
    expect(await iamService.listMembers(signal)).toEqual([member]);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/iam/members"), expect.objectContaining({
      method: "GET", signal,
      headers: expect.objectContaining({ Authorization: "Bearer test-token", "X-Account-Id": "account-1" }),
    }));
  });

  it("attaches and detaches a member's policy at an encoded path", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(null, { status: 204 })));
    vi.stubGlobal("fetch", fetcher);
    await iamService.attachPolicy("member 1", "custom:p1");
    await iamService.detachPolicy("member-1", "MemberAccess");
    expect(fetcher.mock.calls[0][0]).toMatch(/\/iam\/members\/member%201\/policies\/custom%3Ap1$/);
    expect(fetcher.mock.calls[0][1]).toMatchObject({ method: "PUT" });
    expect(fetcher.mock.calls[1][0]).toMatch(/\/iam\/members\/member-1\/policies\/MemberAccess$/);
    expect(fetcher.mock.calls[1][1]).toMatchObject({ method: "DELETE" });
  });

  it("surfaces a refused grant with the API's message", async () => {
    respond({ detail: { code: "ESCALATION", message: "You can only grant permissions you hold yourself" } }, 403);
    await expect(iamService.attachPolicy("member-1", "AdministratorAccess")).rejects.toMatchObject({
      status: 403, message: "You can only grant permissions you hold yourself",
    });
  });

  it("reads one member and their access by service", async () => {
    const fetcher = respond(member);
    expect(await iamService.getMember("member 1")).toEqual(member);
    expect(fetcher.mock.calls[0][0]).toMatch(/\/iam\/members\/member%201$/);
    const access = respond([]);
    await iamService.memberAccess("member-1");
    expect(access.mock.calls[0][0]).toMatch(/\/iam\/members\/member-1\/access$/);
  });

  it("reads a member's effective policies", async () => {
    const fetcher = respond([{ policy: "OwnerAccess", name: "OwnerAccess", description: "", source: "implicit", document: {} }]);
    expect(await iamService.effectivePolicies("member-1")).toHaveLength(1);
    expect(fetcher.mock.calls[0][0]).toMatch(/\/iam\/members\/member-1\/effective-policies$/);
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
