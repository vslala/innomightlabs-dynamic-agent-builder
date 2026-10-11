# IAM Pages Contribution Guide

`/dashboard/iam` is the account-scoped identity/access panel. Its index redirects to `/dashboard/iam/members`; routing stays in `src/App.tsx`. Read the SPA guides and `docs/LLD-account-invitations.md` before changing this flow.

## Ownership

- `IamLayout.tsx` owns the panel heading, Members navigation and nested outlet.
- `MembersPage.tsx` owns asynchronous state, retry and stale-result cancellation.
- `loadMembers.ts` loads capabilities before requesting members. Without `can_list_members`, it must not fetch or expose the member directory—even when `can_invite` is true.
- `MembersPanel.tsx` renders loading, error, empty, read-only and invitation-only states. The Phase 1 email form intentionally cannot submit: delivery/acceptance belong to Phase 2. It stores no draft and displays no fake success.
- `Iam.module.css` owns scoped, token-based layout, table, navigation and form styles. Use shared Button/Input/Label controls; do not add broad global selectors.

Access flags come from `services/iam`, not account role labels or a frontend policy evaluator. Backend checks remain authoritative. Existing account switching reloads the dashboard; do not retain data from a previous account in a new cache.

Permission selection/templates are deferred to Phase 3. Do not silently attach `MemberAccess`, create policies, or expose group selectors as part of the email-only form.

## Verification

From `spa/`, run `yarn test src/pages/dashboard/iam src/services/iam`, focused ESLint on both directories, then the full `yarn test` and `yarn build`. The SSR tests validate state markup and handlers, not browser layout or effect scheduling. Check `/dashboard/iam` redirect, active subnav, owner/list-only/invite-only/no-access views, retry, navigation during loading, narrow widths, both themes and keyboard focus manually. Sending must remain disabled until a real backend flow is integrated.
