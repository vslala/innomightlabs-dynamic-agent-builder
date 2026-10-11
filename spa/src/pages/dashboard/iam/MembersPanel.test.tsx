import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MembersPanel, type MembersState } from "./MembersPanel";
import { IamLayout } from "./IamLayout";

const member = {
  user_id: "owner-1", email: "owner@example.com", name: "Account Owner", status: "active",
  joined_at: "2026-10-01", is_owner: true, group_ids: [], policies: [],
};
function markup(state: MembersState) {
  return renderToStaticMarkup(<MembersPanel state={state} onRetry={vi.fn()} />);
}
function loaded(can_list_members: boolean, can_invite: boolean): MembersState {
  return { status: "loaded", capabilities: { can_list_members, can_invite }, members: [member] };
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

  it("renders loaded members and a labeled, disabled email-only form", () => {
    const html = markup(loaded(true, true));
    expect(html).toContain("Account Owner");
    expect(html).toContain("owner@example.com");
    expect(html).toContain("Owner</span>");
    expect(html).toContain('scope="col"');
    expect(html).toContain('dateTime="2026-10-01"');
    expect(html).toContain('for="iam-invite-email"');
    expect(html).toContain('type="email"');
    expect(html).toMatch(/<button[^>]*type="submit"[^>]*disabled=""/);
    expect(html).toContain("Invitation delivery is not available yet (Phase 2)");
    expect(html).toContain("this email is not saved");
    expect(html.match(/<input /g)).toHaveLength(1);
    expect(html).not.toContain("<select");
  });

  it("prevents form submission and Enter without sending or navigating", () => {
    const form = findForm(MembersPanel({ state: loaded(false, true), onRetry: vi.fn() }));
    expect(form).toBeDefined();
    const preventDefault = vi.fn();
    form?.props.onSubmit?.({ preventDefault } as unknown as React.FormEvent<HTMLFormElement>);
    expect(preventDefault).toHaveBeenCalledOnce();
    preventDefault.mockClear();
    form?.props.onKeyDown?.({ key: "Enter", preventDefault } as unknown as React.KeyboardEvent<HTMLFormElement>);
    expect(preventDefault).toHaveBeenCalledOnce();
    preventDefault.mockClear();
    form?.props.onKeyDown?.({ key: "a", preventDefault } as unknown as React.KeyboardEvent<HTMLFormElement>);
    expect(preventDefault).not.toHaveBeenCalled();
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
    expect(markup({ status: "loaded", capabilities: { can_list_members: true, can_invite: false }, members: [] })).toContain("No members found");
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
