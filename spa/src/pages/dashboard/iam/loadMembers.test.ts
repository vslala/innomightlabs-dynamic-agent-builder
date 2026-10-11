import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { iamService } from "../../../services/iam";
import { loadMembers } from "./loadMembers";
import { invitationService } from "../../../services/iam/invitations";

beforeEach(() => { vi.spyOn(invitationService, "list").mockResolvedValue([]); });

afterEach(() => vi.restoreAllMocks());

describe("capability-gated member loading", () => {
  it("waits for capabilities before requesting members", async () => {
    let resolve!: (value: { can_list_members: boolean; can_invite: boolean }) => void;
    vi.spyOn(iamService, "getCapabilities").mockReturnValue(new Promise((done) => { resolve = done; }));
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    const signal = new AbortController().signal;
    const result = loadMembers(signal);
    expect(list).not.toHaveBeenCalled();
    expect(invitationService.list).not.toHaveBeenCalled();
    resolve({ can_list_members: true, can_invite: false });
    expect(await result).toEqual({ capabilities: { can_list_members: true, can_invite: false }, members: [], invitations: [] });
        expect(invitationService.list).toHaveBeenCalledExactlyOnceWith(signal);
    expect(list).toHaveBeenCalledExactlyOnceWith(signal);
  });

  it.each([true, false])("does not request members without list access (invite=%s)", async (can_invite) => {
    const capabilities = { can_list_members: false, can_invite };
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
      return { can_list_members: true, can_invite: true };
    });
    const list = vi.spyOn(iamService, "listMembers").mockResolvedValue([]);
    await expect(loadMembers(controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(list).not.toHaveBeenCalled();
  });

  it("propagates list failures instead of displaying an empty success", async () => {
    vi.spyOn(iamService, "getCapabilities").mockResolvedValue({ can_list_members: true, can_invite: true });
    vi.spyOn(iamService, "listMembers").mockRejectedValue(new Error("List failed"));
    await expect(loadMembers(new AbortController().signal)).resolves.toMatchObject({
          capabilities: { can_list_members: true, can_invite: true }, directoryError: "List failed",
        });
  });
});
