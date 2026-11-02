# IAM Pages Contribution Guide

`/dashboard/iam` is the account-scoped identity/access panel. Its index redirects to `/dashboard/iam/members`, and `/dashboard/iam/members/:userId` is a member's permissions; routing stays in `src/App.tsx`. Read the SPA guides and `docs/LLD-account-invitations.md` before changing this flow.

## Ownership

- `IamLayout.tsx` owns the panel heading, Members navigation and nested outlet.
- `MembersPage.tsx` owns asynchronous state, retry and stale-result cancellation.
- `loadMembers.ts` loads capabilities before requesting members. Without `can_list_members`, it must not fetch or expose the member directory—even when `can_invite` is true.
- `MembersPanel.tsx` renders loading, error, empty, read-only and invitation-only states. The email-only form submits real invitations; rows expose resend/revoke for invite-capable users. Each member shows their attached policies (Access) and, with `can_view_permissions`, links to their permissions page.
- `loadMemberPermissions.ts` loads capabilities first and requests nothing more without `can_list_members` and `can_view_permissions` (`PermissionsUnavailable`). It then reads the member, the account's policies, their access by service and the policies that apply. Groups are read only to name where a permission comes from, so their failure is not the page's.
- `MemberPermissionsPanel.tsx` renders the member's attached policies (attach and remove with `can_manage_permissions`, never for the owner), their access by service (a table, cards on a phone) and the policies that apply with their JSON. Access comes from the API's summary: never evaluate a policy document in the browser.
- `describeAccess.ts` holds the words: source labels, which policies can be attached, and a service's access as lines (allowed, only on named resources, on what they own, denied). Keep wording there and tested.
- `MemberPermissionsPage.tsx` owns the page state and calls `iamService.attachPolicy` / `detachPolicy`.
- `runMutation.ts` runs one change at a time for both pages, shows success only after API success, and reloads after failure too: an invitation can persist although its email failed, and another admin may have changed the member first (409). Never display a fake success or put a raw token in a dashboard response.
- `people.ts` holds `initials` for avatars.
- `Iam.module.css` owns scoped, token-based layout, table, navigation and form styles. Use shared Button/Input/Label controls; do not add broad global selectors.

Access flags come from `services/iam`, not account role labels or a frontend policy evaluator. Backend checks remain authoritative. Existing account switching reloads the dashboard; do not retain data from a previous account in a new cache.

Invitations stay email-only (Phase 3 decision, `docs/LLD-account-invitations.md`): accepting grants nothing, and an admin attaches policies on the member's page afterwards. Do not add permission or group selectors to the invite form, or attach `MemberAccess` silently. The engine decides every grant (escalation guard, `ACCOUNT_OWNER`); show its message, don't pre-judge it in the browser.

## Verification

From `spa/`, run `yarn test src/pages/dashboard/iam src/services/iam`, focused ESLint on both directories, then the full `yarn test` and `yarn build`. The SSR tests validate state markup and handlers, not browser layout or effect scheduling. Check `/dashboard/iam` redirect, active subnav, owner/list-only/invite-only/no-access views, retry, navigation during loading, narrow widths, both themes and keyboard focus manually. Also check pending/delivery-failed/expired rows, resend rotation, revoke and quota errors, and on a member's page: no policies, attach, remove, an escalation refusal, the owner and read-only views. Missing billing seat metadata is an actionable failure, not a reason to assume unlimited invitations.
