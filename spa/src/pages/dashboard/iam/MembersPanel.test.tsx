import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MembersPanel, type MembersActions, type MembersState } from "./MembersPanel";
import { IamLayout } from "./IamLayout";

const member = {
  user_id: "owner-1", email: "owner@example.com", name: "Account Owner", status: "active",
  joined_at: "2026-10-01", is_owner: true, group_ids: [], policies: [],
};
const actions: MembersActions = { pending: false, onInvite: vi.fn(), onResend: vi.fn(), onRevoke: vi.fn() };
function markup(state: MembersState, overrides: Partial<MembersActions> = {}) {
  return renderToStaticMarkup(<MembersPanel state={state} onRetry={vi.fn()} actions={{ ...actions, ...overrides }} />);
}
function loaded(can_list_members: boolean, can_invite: boolean): MembersState {
  return { status: "loaded", capabilities: { can_list_members, can_invite }, members: [member], invitations: [] };
}

function findForm(node: React.ReactNode): React.ReactElement<React.ComponentProps<"form">> | undefined {
  if (!React.isValidElement<{ children?: React.ReactNode }>(node)) return undefined;
  if (node.type === "form") return node as React.ReactElement<React.ComponentProps<"form">>;
  for (const child of React.Children.toArray(node.props.children)) {
    const form = findForm(child);
    if (form) return form;
  }
  return undefined;
}

describe("members UI", () => {
  it("shows loading without an invite form or table", () => {
    const html = markup({ status: "loading" });
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('role="status"');
    expect(html).not.toContain("<table");
    expect(html).not.toContain("<form");
  });

  it("renders loaded members and a required, real email-only form", () => {
    const html = markup(loaded(true, true));
    expect(html).toContain("Account Owner");
    expect(html).toContain("owner@example.com");
    expect(html).toContain("Owner</span>");
    expect(html).toContain('scope="col"');
    expect(html).toContain('dateTime="2026-10-01"');
    expect(html).toContain('for="iam-invite-email"');
    expect(html).toContain('type="email"');
    expect(html).not.toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(html).toMatch(/<input[^>]*required=""/);
    expect(html).not.toContain("Phase 2");
    expect(html.match(/<input /g)).toHaveLength(1);
    expect(html).not.toContain("<select");
  });

  it("submits only an email through the page handler and blocks pending submissions", () => {
    const onInvite = vi.fn();
    const formData = new FormData();
    formData.set("email", " invited@example.com ");
    vi.stubGlobal("FormData", class { get(key: string) { return formData.get(key); } });
    try {
      const preventDefault = vi.fn();
      const event = { preventDefault, currentTarget: {} } as unknown as React.FormEvent<HTMLFormElement>;
      const form = findForm(MembersPanel({ state: loaded(false, true), onRetry: vi.fn(), actions: { ...actions, onInvite } }));
      form?.props.onSubmit?.(event);
      expect(preventDefault).toHaveBeenCalledOnce();
      expect(onInvite).toHaveBeenCalledExactlyOnceWith("invited@example.com");
      const pendingForm = findForm(MembersPanel({ state: loaded(false, true), onRetry: vi.fn(), actions: { ...actions, pending: true, onInvite } }));
      pendingForm?.props.onSubmit?.(event);
      expect(onInvite).toHaveBeenCalledOnce();
      expect(markup(loaded(false, true), { pending: true })).toContain("Working…");
      expect(markup(loaded(false, true), { pending: true })).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    } finally { vi.unstubAllGlobals(); }
  });

  it("shows read-only list access without the form", () => {
    const html = markup(loaded(true, false));
    expect(html).toContain("Read-only access");
    expect(html).toContain("<table");
    expect(html).not.toContain("<form");
  });

  it("shows invite-only access without exposing even supplied member data", () => {
    const html = markup(loaded(false, true));
    expect(html).toContain("do not have access to the member list");
    expect(html).toContain("<form");
    expect(html).not.toContain("<table");
    expect(html).not.toContain(member.email);
  });

  it("explains unavailable access without list or form", () => {
    const html = markup(loaded(false, false));
    expect(html).toContain("Member access is unavailable");
    expect(html).not.toContain("<table");
    expect(html).not.toContain("<form");
  });

  it("shows the empty state only when listing is allowed", () => {
    expect(markup({ status: "loaded", capabilities: { can_list_members: true, can_invite: false }, members: [], invitations: [] })).toContain("No members found");
    expect(markup(loaded(false, true))).not.toContain("No members found");
  });

  it("shows an actionable error without a success surface", () => {
    const html = markup({ status: "error", message: "Missing iam:ListMembers" });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Unable to load members");
    expect(html).toContain("Missing iam:ListMembers");
    expect(html).toContain("Retry</button>");
    expect(html).not.toContain("<table");
    expect(html).not.toContain("<form");
  });

  it("keeps the invite form visible on directory failure and displays real mutation errors", () => {
    const state = { ...loaded(true, true), directoryError: "Missing iam:ListMembers" } as MembersState;
    const html = markup(state, { error: "Seat limit reached. Ask your administrator to upgrade." });
    expect(html).toContain("<form");
    expect(html).toContain("Missing iam:ListMembers");
    expect(html).toContain("Seat limit reached");
    expect(html).not.toContain("Invitation sent.");
  });

  it("gates invitation rows and actions independently", () => {
    const invitation = { account_id: "a", invite_id: "i", email: "invited@example.com", invited_by: "u", expires_at: "2026-11-01", status: "expired" as const, delivery_status: "failed" as const, accepted_by: null, created_at: "2026-10-01" };
    const state = { ...loaded(true, true), invitations: [invitation] } as MembersState;
    expect(markup(state)).toContain("Expired</span>");
    expect(markup(state)).toContain("Delivery failed</span>");
    expect(markup(state)).toContain("Resend</button>");
    expect(markup(state)).toContain("Revoke</button>");
    expect(markup({ ...loaded(true, false), invitations: [invitation] } as MembersState)).not.toContain("Resend</button>");
    expect(markup({ ...loaded(false, true), invitations: [invitation] } as MembersState)).not.toContain(invitation.email);
  });

  it("exports a nested layout with semantic current navigation and an outlet", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter initialEntries={["/dashboard/iam/members"]}>
        <Routes>
          <Route path="/dashboard/iam" element={<IamLayout />}>
            <Route path="members" element={<p>Outlet content</p>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(html).toContain('<nav aria-label="Identity and access"');
    expect(html).toContain('aria-current="page"');
    expect(html).toContain('href="/dashboard/iam/members"');
    expect(html).toContain("Outlet content");
  });
});
