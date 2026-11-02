import {
  iamService,
  type EffectivePolicy,
  type IamCapabilities,
  type IamMember,
  type PolicySummary,
  type ServiceAccess,
} from "../../../services/iam";

export interface MemberPermissionsData {
  capabilities: IamCapabilities;
  member: IamMember;
  /** Every policy in the account, built-in and custom, for the picker */
  policies: PolicySummary[];
  access: ServiceAccess[];
  effective: EffectivePolicy[];
  groupNames: Map<string, string>;
}

/** Thrown when the caller may not see this member's permissions. */
export class PermissionsUnavailable extends Error {}

export async function loadMemberPermissions(userId: string, signal: AbortSignal): Promise<MemberPermissionsData> {
  const capabilities = await iamService.getCapabilities(signal);
  signal.throwIfAborted();
  if (!capabilities.can_list_members || !capabilities.can_view_permissions) {
    throw new PermissionsUnavailable("You don't have permission to see members' permissions in this account.");
  }
  const [member, policies, access, effective, groups] = await Promise.all([
    iamService.getMember(userId, signal),
    iamService.listPolicies(signal),
    iamService.memberAccess(userId, signal),
    iamService.effectivePolicies(userId, signal),
    // Only names a group a permission comes from, so the page still works without iam:ListGroups
    iamService.listGroups(signal).catch(() => []),
  ]);
  signal.throwIfAborted();
  return {
    capabilities, member, policies, access, effective,
    groupNames: new Map(groups.map((group) => [group.group_id, group.name])),
  };
}
