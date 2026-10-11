# Dashboard Shell Contribution Guide

## Purpose and layout

This module supplies signed-in chrome, not resource CRUD pages.

- `DashboardLayout.tsx` / `.css`: Sidebar + Header + scrolling main + OAuthReturn + route Outlet. Owns whether the navigation drawer is open.
- `Sidebar.tsx` / `.css`: navigation, imported brand logo, logout through authService. A fixed column on desktop, an off-canvas drawer below 900px.
- `Header.tsx` / `.css`: menu button (drawer only), account switcher, route title, user/avatar settings link.
- `AccountSwitcher.tsx` / `.css`: active memberships and account selection.
- `OAuthReturn.tsx`: sealed OAuth completion before children render.

## Flow and extension

`ProtectedRoute` validates the session outside this shell. DashboardLayout reads the user from the token and supplies `{ user }` through the Outlet context. Its exact title map and nested-path checks are presentation only; routes are declared in `src/App.tsx`. Add navigation/title treatment alongside a new page where appropriate, not a second route table.

Conversations and matching automation workspace routes are full-bleed. The automation matcher excludes `marketplace`; settings temporarily controls body overflow and HTML overscroll and restores prior values on cleanup. Preserve `min-height: 0` and overflow ownership when changing flex layouts—nested workspaces depend on contained scrolling.

AccountSwitcher loads memberships, selects the service's current account, pins this tab's active account id for HTTP, and offers active memberships. Switching calls the service and performs `window.location.assign("/dashboard")` so previous-account data does not remain onscreen. Do not replace this with a cosmetic selection unless data invalidation is handled deliberately. The UI role label is not authorization.

OAuthReturn detects `oauth_complete` on mount, posts the sealed completion to `/connectors/oauth/complete` through httpClient, replaces it with returned result parameters, and only then renders children. Failure sets `skill_oauth=error`. A ref prevents duplicate completion starts; do not move raw completion handling into every page or log handoff values. This is separate from the chat connection popup UI.

## CSS and accessibility

`DashboardLayout.css` and `AccountSwitcher.css` are plain global CSS with `dashboard-layout__*` and `account-switcher*` prefixes, not CSS modules. Header/Sidebar also use utilities and inline styles. Keep global selectors tightly scoped; use local modules for new isolated styling rather than broad element overrides. Follow shared surface/text/nav/spacing tokens and compact operational UI conventions.

Use actual navigation links and preserve active-route semantics, keyboard focus, accessible account-switch labels, and meaningful avatar alt text. ## Responsive behaviour

One breakpoint, 900px, shared by `DashboardLayout.tsx` (`COMPACT_QUERY`), `Sidebar.css` and `Header.css`: change them together.

- **Below 900px** the sidebar is a drawer. The header shows a menu button (`aria-controls`, `aria-expanded`) and the layout order becomes menu, title, account, avatar. The drawer closes on navigation, Escape, the backdrop or its close button; while it is open the rest of the app is `inert` and focus moves into it, then back to the menu button on Escape or close. A closed drawer is `inert` and `visibility: hidden`, so it is not in the tab order.
- **The drawer's open state is the path it was opened on** (`drawerPath`), so any navigation closes it without an effect, and widening the window clears it so narrowing again does not bring it back.
- **`--dashboard-gutter`** (32, 24, 16px) is the page padding, set on `.dashboard-layout`. Secondary navigation that bleeds to the screen edge reads it (see `AgentSideNav.css`).
- **Secondary navigation** (a page's own section list: the agent tabs in `AgentSideNav.css`, the Google/MCP list in `ConnectorsPage.module.css`) sits directly under the header on narrow screens as a horizontally scrolling tab bar. Three things make it work, and each has bitten us:
  - It is `position: sticky` with `top: calc(var(--dashboard-gutter) * -1)`. Sticky offsets are measured inside the scroll area's padding, so `top: 0` leaves a gap of one gutter that content shows through.
  - Its parent must be a flex column, not a one-column grid: a grid item can only stick within its own row.
  - That column needs `align-items: stretch`. The desktop rule says `start`, which sizes the bar to its content (the whole tab list), widens the page and makes it pan sideways.
  Scroll the active tab into view.
- Use `100dvh`, not only `100vh`, for full-height shells: mobile browsers' address bars change the viewport height.
- Check keyboard and narrow-screen usability (about 390px wide) before extending the shell. A screenshot is not enough to catch sideways overflow: compare the scroll area's `scrollWidth` with its `clientWidth` at 390px (`.dashboard-layout__main`); they must be equal.

## Verification

No shell tests are colocated here. Add focused coverage for new route classification or handoff logic where useful. Manually check exact/nested titles, sidebar selection, conversations/full-bleed automation pages, settings scroll restoration, account switching and stale-data absence, OAuth success/error/duplicate-start behavior, logout, long account names, and both themes. From `spa/`, run focused ESLint, `yarn build`, and `yarn design:audit` for implementation changes.
