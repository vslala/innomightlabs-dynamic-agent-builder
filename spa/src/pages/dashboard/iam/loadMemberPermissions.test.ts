import { afterEach, describe, expect, it, vi } from "vitest";
import { HttpError } from "../../../services/http/client";
import { iamService, type IamCapabilities, type IamMember } from "../../../services/iam";
import { loadMemberPermissions, PermissionsUnavailable } from "./loadMemberPermissions";

const ALL: IamCapabilities = { can_list_members: true, can_invite: true, can_view_permissions: true, can_manage_permissions: true };
const member: IamMember = {
  user_id: "u1", email: "priya@example.com", name: "Priya", status: "active", joined_at: "2026-11-01",
  is_owner: false, group_ids: ["g1"], policies: [],
};

afterEach(() => vi.restoreAllMocks());

function stubReads(capabilities: IamCapabilities = ALL) {
  vi.spyOn(iamService, "getCapabilities").mockResolvedValue(capabilities);
  return {
    member: vi.spyOn(iamService, "getMember").mockResolvedValue(member),
    policies: vi.spyOn(iamService, "listPolicies").mockResolvedValue([]),
    access: vi.spyOn(iamService, "memberAccess").mockResolvedValue([]),
    effective: vi.spyOn(iamService, "effectivePolicies").mockResolvedValue([]),
    groups: vi.spyOn(iamService, "listGroups").mockResolvedValue([
      { group_id: "g1", name: "Support", description: "", member_ids: ["u1"], policies: [], created_at: "" },
    ]),
  };
}

describe("loading a member's permissions", () => {
  it("loads the member, their access, every policy and group names", async () => {
    const reads = stubReads();
    const signal = new AbortController().signal;

    const data = await loadMemberPermissions("u1", signal);

    expect(data.member).toEqual(member);
    expect(data.groupNames.get("g1")).toBe("Support");
    expect(reads.member).toHaveBeenCalledExactlyOnceWith("u1", signal);
    expect(reads.access).toHaveBeenCalledExactlyOnceWith("u1", signal);
    expect(reads.effective).toHaveBeenCalledExactlyOnceWith("u1", signal);
  });

  it.each([
    { ...ALL, can_view_permissions: false },
    { ...ALL, can_list_members: false },
  ])("requests nothing more without permission to see it (%o)", async (capabilities) => {
    const reads = stubReads(capabilities);

    await expect(loadMemberPermissions("u1", new AbortController().signal)).rejects.toBeInstanceOf(PermissionsUnavailable);
    expect(reads.member).not.toHaveBeenCalled();
    expect(reads.access).not.toHaveBeenCalled();
  });

  it("surfaces a person who isn't a member as the API's not found", async () => {
    const reads = stubReads();
    reads.member.mockRejectedValue(new HttpError(404, "There is no such member"));

    await expect(loadMemberPermissions("someone-else", new AbortController().signal)).rejects.toThrow("There is no such member");
  });

  it("still loads without access to groups, naming none", async () => {
    const reads = stubReads();
    reads.groups.mockRejectedValue(new Error("Missing iam:ListGroups"));

    const data = await loadMemberPermissions("u1", new AbortController().signal);

    expect(data.groupNames.size).toBe(0);
  });

  it("surfaces a failed read instead of showing no permissions", async () => {
    const reads = stubReads();
    reads.access.mockRejectedValue(new Error("Service unavailable"));
    await expect(loadMemberPermissions("u1", new AbortController().signal)).rejects.toThrow("Service unavailable");
  });
});
