import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { iamService, type IamCapabilities } from "../../../services/iam";
import { loadMembers } from "./loadMembers";
import { invitationService } from "../../../services/iam/invitations";

beforeEach(() => { vi.spyOn(invitationService, "list").mockResolvedValue([]); });

afterEach(() => vi.restoreAllMocks());

const NO_PERMISSIONS = { can_view_permissions: false, can_manage_permissions: false };

describe("capability-gated member loading", () => {
  it("waits for capabilities before requesting members", async () => {
    let resolve!: (value: IamCapabilities) => void;
    vi.spyOn(iamService, "getCapabilities").mockReturnValue(new Promise((done) => { resolve = done; }));
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    const signal = new AbortController().signal;
    const result = loadMembers(signal);
    expect(list).not.toHaveBeenCalled();
    expect(invitationService.list).not.toHaveBeenCalled();
    resolve({ can_list_members: true, can_invite: false, ...NO_PERMISSIONS });
    expect(await result).toEqual({ capabilities: { can_list_members: true, can_invite: false, ...NO_PERMISSIONS }, members: [], invitations: [] });
        expect(invitationService.list).toHaveBeenCalledExactlyOnceWith(signal);
    expect(list).toHaveBeenCalledExactlyOnceWith(signal);
  });

  it.each([true, false])("does not request members without list access (invite=%s)", async (can_invite) => {
    const capabilities = { can_list_members: false, can_invite, ...NO_PERMISSIONS };
    vi.spyOn(iamService, "getCapabilities").mockResolvedValue(capabilities);
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    expect(await loadMembers(new AbortController().signal)).toEqual({ capabilities, members: [], invitations: [] });
    expect(list).not.toHaveBeenCalled();
    expect(invitationService.list).not.toHaveBeenCalled();
  });

  it("does not request members if capabilities fail", async () => {
    vi.spyOn(iamService, "getCapabilities").mockRejectedValue(new Error("Access unavailable"));
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    await expect(loadMembers(new AbortController().signal)).rejects.toThrow("Access unavailable");
    expect(list).not.toHaveBeenCalled();
  });

  it("does not start a member request after cancellation", async () => {
    const controller = new AbortController();
    vi.spyOn(iamService, "getCapabilities").mockImplementation(async () => {
      controller.abort();
      return { can_list_members: true, can_invite: true, ...NO_PERMISSIONS };
    });
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    await expect(loadMembers(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(list).not.toHaveBeenCalled();
  });

  it("propagates list failures instead of displaying an empty success", async () => {
    vi.spyOn(iamService, "getCapabilities").mockResolvedValue({ can_list_members: true, can_invite: true, ...NO_PERMISSIONS });
    vi.spyOn(iamService, "listMembers").mockRejectedValue(new Error("List failed"));
    await expect(loadMembers(new AbortController().signal)).resolves.toMatchObject({
          capabilities: { can_list_members: true, can_invite: true, ...NO_PERMISSIONS }, directoryError: "List failed",
        });
  });
});
