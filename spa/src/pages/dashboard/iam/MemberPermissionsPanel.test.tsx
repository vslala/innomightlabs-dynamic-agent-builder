import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { EffectivePolicy, IamCapabilities, IamMember, PolicySummary, ServiceAccess } from "../../../services/iam";
import { MemberPermissionsPanel, type MemberPermissionsActions, type MemberPermissionsState } from "./MemberPermissionsPanel";

const ALL: IamCapabilities = { can_list_members: true, can_invite: true, can_view_permissions: true, can_manage_permissions: true };
const member: IamMember = {
  user_id: "u1", email: "priya@example.com", name: "Priya Yadav", status: "active", joined_at: "2026-11-01",
  is_owner: false, group_ids: [], policies: [],
};
const policies: PolicySummary[] = [
  { policy: "OwnerAccess", name: "OwnerAccess", description: "Everything they own.", builtin: true, attachment_count: 0 },
  { policy: "MemberAccess", name: "MemberAccess", description: "Create their own resources.", builtin: true, attachment_count: 0 },
  { policy: "custom:p1", name: "Support", description: "Chat with support agents.", builtin: false, attachment_count: 1 },
];
const effective: EffectivePolicy[] = [{
  policy: "OwnerAccess", name: "OwnerAccess", description: "Everything they own.", source: "implicit",
  document: { Version: "2026-10-10", Statement: [] },
}];
const nowhere = { scope: null, resources: [], policies: [] };
const access: ServiceAccess[] = [
  {
    service: "agents", label: "Agents", summary: "Agents and chatting with them", level: "limited",
    actions: [
      { action: "agents:Create", verb: "Create", level: "none", allow: nowhere, deny: nowhere },
      { action: "agents:Chat", verb: "Chat", level: "own", allow: { scope: "own", resources: [], policies: ["OwnerAccess"] }, deny: nowhere },
    ],
  },
  {
    service: "billing", label: "Billing", summary: "The account's plan", level: "none",
    actions: [{ action: "billing:View", verb: "View", level: "none", allow: nowhere, deny: nowhere }],
  },
];
const actions: MemberPermissionsActions = { pending: false, onAttach: vi.fn(), onDetach: vi.fn() };

function loaded(overrides: { member?: Partial<IamMember>; capabilities?: Partial<IamCapabilities> } = {}): MemberPermissionsState {
  return {
    status: "loaded", policies, effective, access, groupNames: new Map(),
    member: { ...member, ...overrides.member }, capabilities: { ...ALL, ...overrides.capabilities },
  };
}

function markup(state: MemberPermissionsState, overrides: Partial<MemberPermissionsActions> = {}) {
  return renderToStaticMarkup(
    <MemoryRouter><MemberPermissionsPanel state={state} onRetry={vi.fn()} actions={{ ...actions, ...overrides }} /></MemoryRouter>,
  );
}

describe("member permissions UI", () => {
  it("shows loading, with a way back to the members", () => {
    const html = markup({ status: "loading" });
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('role="status"');
    expect(html).toContain('href="/dashboard/iam/members"');
  });

  it("shows an error with a retry", () => {
    const html = markup({ status: "error", message: "You don't have permission" });
    expect(html).toContain("Unable to load permissions");
    expect(html).toContain("Retry");
  });

  it("offers to attach a policy to a member with none", () => {
    const html = markup(loaded());
    expect(html).toContain("Priya Yadav");
    expect(html).toContain("No policies attached");
    expect(html).toContain("Add a policy");
    expect(html).toContain("<form");
  });

  it("lists attached policies by name with a remove action", () => {
    const html = markup(loaded({ member: { policies: [
      { policy: "MemberAccess", name: "MemberAccess" }, { policy: "custom:p1", name: "Support" },
    ] } }));
    expect(html).toContain("Create their own resources.");
    expect(html).toContain("Custom");
    expect(html).toContain('aria-label="Remove MemberAccess"');
    expect(html).toContain('aria-label="Remove Support"');
  });

  it("is read-only without permission to change permissions", () => {
    const html = markup(loaded({ member: { policies: [{ policy: "MemberAccess", name: "MemberAccess" }] }, capabilities: { can_manage_permissions: false } }));
    expect(html).toContain("Read-only access");
    expect(html).not.toContain("Remove MemberAccess");
    expect(html).not.toContain("<form");
  });

  it("never offers to change the account owner", () => {
    const html = markup(loaded({ member: { is_owner: true } }));
    expect(html).toContain("always has full access");
    expect(html).not.toContain("Add a policy");
    expect(html).not.toContain("<form");
  });

  it("shows access service by service, with what each allows", () => {
    const html = markup(loaded());
    expect(html).toContain("Access by service");
    expect(html).toContain("Agents");
    expect(html).toContain("Limited");
    expect(html).toContain("On what they own");
    expect(html).toContain("Chat");
    expect(html).toContain("No access");
  });

  it("shows where access comes from, with the policy JSON on request", () => {
    const html = markup(loaded());
    expect(html).toContain("Policies that apply");
    expect(html).toContain("Applies to every member");
    expect(html).toContain("View JSON");
  });

  it("shows a failed change as an error and a successful one as a status", () => {
    expect(markup(loaded(), { error: "You can only grant permissions you hold yourself" })).toContain('role="alert"');
    expect(markup(loaded(), { success: "Policy attached." })).toContain("Policy attached.");
  });
});
