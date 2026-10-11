# Components Contribution Guide

Read `spa/AGENTS.md`, `spa/SKILLS.md`, and `CODE_PHILOSOPHY.md` first. Paths below are relative to `spa/` unless stated otherwise.

## Purpose and layout

This directory holds reusable React surfaces, not the route table or all page state. Routes are composed in `src/App.tsx`; API operations normally belong to singleton services under `src/services/`, using the shared HTTP client.

| Area | Responsibility | Guide |
| --- | --- | --- |
| `ui/` | Shared controls, feedback, cards, and content viewers | [ui](ui/CONTRIBUTION.md) |
| `layout/` | Page, section, stack, and form composition | [layout](layout/CONTRIBUTION.md) |
| `forms/` | Backend-schema editing and read-only rendering | [forms](forms/CONTRIBUTION.md) |
| `chat/` | Composer, transcript, tools, forms, connections, and canvases | [chat](chat/CONTRIBUTION.md) |
| `auth/` | Session-validation route wrapper | [auth](auth/CONTRIBUTION.md) |
| `dashboard/` | Signed-in shell, account switcher, OAuth handoff | [dashboard](dashboard/CONTRIBUTION.md) |
| `docs/` | Public documentation shell and section navigation | [docs](docs/CONTRIBUTION.md) |
| `landing/` | Scripted Ila demo and scene helpers | [landing](landing/CONTRIBUTION.md) |

Root components include `Navbar`, `Footer`, `Hero`, `Features`, `HowItWorks`, `WaitlistForm`, `BetaBanner`, `RateLimitBanner`, and `SiteConcierge`. `WaitlistForm` owns its email/status state and calls `subscriptionService.subscribe`; do not confuse it with schema-driven account settings forms.

## Composition and extension

Pages pass data and callbacks into shared components. Keep local interaction state local; do not move domain fetching or route orchestration into a primitive. Prefer `ui` controls and `layout` composition before inventing equivalent local buttons, dialogs, or spacing wrappers. Add a domain-specific reusable surface in its meaningful module; do not add speculative registries or a universal component abstraction.

`SiteConcierge` injects the public embed loader once because the loader has no teardown. Route changes toggle `body[data-concierge-hidden]`; `src/index.css` hides the launcher on dashboard routes. Preserve this pairing and script deduplication. The widget implementation lives outside this directory in `embed/`, not in dashboard chat.

## CSS and accessibility

Most components pair PascalCase `.tsx` files with `.module.css`, imported as `styles`; these classes are scoped. Dashboard shell CSS is deliberately plain/global with prefixed class names. Follow the local style rather than treating every CSS import as a module. Some existing components also use utilities and inline styles; new substantial static styling belongs in a local stylesheet, with inline styles reserved for dynamic values where practical.

Use `src/styles/tokens.css` for theme colors, surfaces, borders, spacing, radii, and control dimensions. Tokens are shared with the embed widget. Avoid hardcoded dark-theme assumptions; check light and dark themes. Reuse semantic controls, visible focus, labels for icon-only actions, and non-color status cues. Use `aria-current` for navigation and do not turn a clickable `div` into a substitute for a link or button.

## Verification

From `spa/`, run the focused test files named by each module guide. Existing tests cover helpers; they do not prove browser interaction or accessibility. Manually inspect the consuming page at narrow and wide widths, both themes, keyboard-only navigation, and loading/error/empty states. For implementation changes run focused ESLint, `yarn build`, and `yarn design:audit`; the audit flags raw controls outside `ui` and is not an accessibility test. Run the area suite according to `spa/AGENTS.md` when not delegated to a parent task. Documentation-only edits need path/link review, not a claim that runtime tests passed.
