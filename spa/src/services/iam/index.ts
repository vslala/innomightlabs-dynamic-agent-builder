import { httpClient } from "../http/client";

/** What the caller may do in this account, for which controls to show. The API still decides every request. */
export interface IamCapabilities {
  can_list_members: boolean;
  can_invite: boolean;
  can_view_permissions: boolean;
  can_manage_permissions: boolean;
}

/** A policy as attachments name it (`MemberAccess`, `custom:{id}`) and as people read it. */
export interface PolicyRef {
  policy: string;
  name: string;
}

export interface IamMember {
  user_id: string;
  email: string;
  name: string;
  status: string;
  joined_at: string;
  is_owner: boolean;
  group_ids: string[];
  /** Attached directly */
  policies: PolicyRef[];
}

export interface PolicySummary {
  /** What attachments name: a built-in name or `custom:{policy_id}` */
  policy: string;
  name: string;
  description: string;
  builtin: boolean;
  default_version?: number | null;
  attachment_count: number;
}

export interface EffectivePolicy extends PolicyRef {
  description: string;
  /** "implicit", "account owner", "direct" or "group:{group_id}" */
  source: string;
  /** The policy JSON as written */
  document: Record<string, unknown>;
}

/** How far an Allow or a Deny reaches: every resource, the ones named, or the ones the member owns. */
export interface Reach {
  scope: "all" | "some" | "own" | null;
  resources: string[];
  policies: string[];
}

export type ActionLevel = "all" | "some" | "own" | "denied" | "none";

export interface ActionAccess {
  action: string;
  verb: string;
  level: ActionLevel;
  allow: Reach;
  deny: Reach;
}

/** One service's actions under the member's policies, as the API summarises them (shares not included). */
export interface ServiceAccess {
  service: string;
  label: string;
  summary: string;
  level: "full" | "limited" | "none";
  actions: ActionAccess[];
}

export interface IamGroup {
  group_id: string;
  name: string;
  description: string;
  member_ids: string[];
  policies: string[];
  created_at: string;
}

function memberPolicyPath(userId: string, policy: string): string {
  return `/iam/members/${encodeURIComponent(userId)}/policies/${encodeURIComponent(policy)}`;
}

class IamService {
  async getCapabilities(signal?: AbortSignal): Promise<IamCapabilities> {
    return httpClient.get<IamCapabilities>("/iam/capabilities", { signal });
  }

  async listMembers(signal?: AbortSignal): Promise<IamMember[]> {
    return httpClient.get<IamMember[]>("/iam/members", { signal });
  }

  async getMember(userId: string, signal?: AbortSignal): Promise<IamMember> {
    return httpClient.get<IamMember>(`/iam/members/${encodeURIComponent(userId)}`, { signal });
  }

  async memberAccess(userId: string, signal?: AbortSignal): Promise<ServiceAccess[]> {
    return httpClient.get<ServiceAccess[]>(`/iam/members/${encodeURIComponent(userId)}/access`, { signal });
  }

  async listGroups(signal?: AbortSignal): Promise<IamGroup[]> {
    return httpClient.get<IamGroup[]>("/iam/groups", { signal });
  }

  async listPolicies(signal?: AbortSignal): Promise<PolicySummary[]> {
    return httpClient.get<PolicySummary[]>("/iam/policies", { signal });
  }

  async effectivePolicies(userId: string, signal?: AbortSignal): Promise<EffectivePolicy[]> {
    return httpClient.get<EffectivePolicy[]>(`/iam/members/${encodeURIComponent(userId)}/effective-policies`, { signal });
  }

  async attachPolicy(userId: string, policy: string): Promise<void> {
    await httpClient.request<void>(memberPolicyPath(userId, policy), { method: "PUT" });
  }

  async detachPolicy(userId: string, policy: string): Promise<void> {
    await httpClient.request<void>(memberPolicyPath(userId, policy), { method: "DELETE" });
  }
}

export const iamService = new IamService();
