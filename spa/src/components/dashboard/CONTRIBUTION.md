# Dashboard Shell Contribution Guide

## Purpose and layout

This module supplies signed-in chrome, not resource CRUD pages.

- `DashboardLayout.tsx` / `.css`: Sidebar + Header + scrolling main + OAuthReturn + route Outlet.
- `Sidebar.tsx`: navigation, imported brand logo, logout through authService.
- `Header.tsx`: account switcher, route title, user/avatar settings link.
- `AccountSwitcher.tsx` / `.css`: active memberships and account selection.
- `OAuthReturn.tsx`: sealed OAuth completion before children render.

## Flow and extension

`ProtectedRoute` validates the session outside this shell. DashboardLayout reads the user from the token and supplies `{ user }` through the Outlet context. Its exact title map and nested-path checks are presentation only; routes are declared in `src/App.tsx`. Add navigation/title treatment alongside a new page where appropriate, not a second route table.

Conversations and matching automation workspace routes are full-bleed. The automation matcher excludes `marketplace`; settings temporarily controls body overflow and HTML overscroll and restores prior values on cleanup. Preserve `min-height: 0` and overflow ownership when changing flex layouts—nested workspaces depend on contained scrolling.

AccountSwitcher loads memberships, selects the service's current account, pins this tab's active account id for HTTP, and offers active memberships. Switching calls the service and performs `window.location.assign("/dashboard")` so previous-account data does not remain onscreen. Do not replace this with a cosmetic selection unless data invalidation is handled deliberately. The UI role label is not authorization.

OAuthReturn detects `oauth_complete` on mount, posts the sealed completion to `/connectors/oauth/complete` through httpClient, replaces it with returned result parameters, and only then renders children. Failure sets `skill_oauth=error`. A ref prevents duplicate completion starts; do not move raw completion handling into every page or log handoff values. This is separate from the chat connection popup UI.

## CSS and accessibility

`DashboardLayout.css` and `AccountSwitcher.css` are plain global CSS with `dashboard-layout__*` and `account-switcher*` prefixes, not CSS modules. Header/Sidebar also use utilities and inline styles. Keep global selectors tightly scoped; use local modules for new isolated styling rather than broad element overrides. Follow shared surface/text/nav/spacing tokens and compact operational UI conventions.

Use actual navigation links and preserve active-route semantics, keyboard focus, accessible account-switch labels, and meaningful avatar alt text. Do not assume the fixed-width sidebar already provides mobile collapse behavior. Check keyboard and narrow-screen usability before extending it.

## Verification

No shell tests are colocated here. Add focused coverage for new route classification or handoff logic where useful. Manually check exact/nested titles, sidebar selection, conversations/full-bleed automation pages, settings scroll restoration, account switching and stale-data absence, OAuth success/error/duplicate-start behavior, logout, long account names, and both themes. From `spa/`, run focused ESLint, `yarn build`, and `yarn design:audit` for implementation changes.
