import { afterEach, describe, expect, it, vi } from "vitest";
import { InvitationError, invitationService } from "../../../services/iam/invitations";
import { mutateInvitation } from "./mutateInvitation";
import { loadMembers, type MembersData } from "./loadMembers";

afterEach(() => vi.unstubAllGlobals());

describe("invitation mutations", () => {
  it("reports pending immediately, blocks duplicate in-flight actions, and reloads only after success", async () => {
    const lock = { current: false };
    let finish!: () => void;
    const operation = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
    const report = vi.fn();
    const reload = vi.fn();
    const first = mutateInvitation(lock, operation, "Invitation sent.", report, reload);
    expect(report).toHaveBeenCalledExactlyOnceWith({ pending: true });
    expect(reload).not.toHaveBeenCalled();
    await mutateInvitation(lock, operation, "Invitation sent.", report, reload);
    expect(operation).toHaveBeenCalledOnce();
    finish();
    await first;
    expect(report).toHaveBeenLastCalledWith({ pending: false, success: "Invitation sent." });
    expect(reload).toHaveBeenCalledOnce();
    expect(lock.current).toBe(false);
  });
  it("reloads directory and the persisted invite after a real shared-client delivery failure", async () => {
    vi.stubGlobal("localStorage", { getItem: () => null });
    const invite = { account_id: "account", invite_id: "persisted", email: "invite@example.com", invited_by: "owner", expires_at: "2026-11-01", status: "pending", delivery_status: "failed", accepted_by: null, created_at: "2026-10-01" };
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: { code: "MAIL_DELIVERY_FAILED", message: "Email failed. Please resend.", invite_id: invite.invite_id } }), { status: 502 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ can_list_members: true, can_invite: true })))
      .mockResolvedValueOnce(new Response(JSON.stringify([])))
      .mockResolvedValueOnce(new Response(JSON.stringify([invite])));
    vi.stubGlobal("fetch", fetcher);
    const report = vi.fn();
    let refreshed: Promise<MembersData> | undefined;
    const reload = vi.fn(() => { refreshed = loadMembers(new AbortController().signal); });
    await mutateInvitation({ current: false }, () => invitationService.create(invite.email), "Invitation sent.", report, reload);
    expect(report).toHaveBeenLastCalledWith({ pending: false, error: "Email failed. Please resend." });
    expect(report.mock.calls.some(([state]) => state.success)).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
    expect(await refreshed).toMatchObject({ members: [], invitations: [invite] });
    expect(fetcher.mock.calls.map(([url]) => new URL(String(url)).pathname)).toEqual([
      "/iam/invitations", "/iam/capabilities", "/iam/members", "/iam/invitations",
    ]);
  });

  it.each([
    [502, "MAIL_DELIVERY_FAILED", "Email failed. Please resend.", "Email failed. Please resend."],
    [409, "SEAT_LIMIT_REACHED", "Seats full.", "administrator"],
    [409, "SEAT_LIMIT_UNAVAILABLE", "Seats unavailable.", "billing"],
    [429, "RATE_LIMIT", "Please wait.", "Please wait."],
  ])("does not show success on %s/%s and reloads persisted state", async (status, code, message, expected) => {
    const report = vi.fn();
    const reload = vi.fn();
    await mutateInvitation({ current: false }, () => Promise.reject(new InvitationError(Number(status), { code: String(code), message: String(message), invite_id: "persisted" })), "Invitation sent.", report, reload);
    expect(report).toHaveBeenLastCalledWith({ pending: false, error: expect.stringContaining(String(expected)) });
    expect(report.mock.calls.some(([state]) => state.success)).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
  });
});
