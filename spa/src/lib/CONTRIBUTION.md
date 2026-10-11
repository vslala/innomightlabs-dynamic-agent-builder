# Frontend Library Contribution Guide

## Purpose and layout

This is a small shared frontend foundation, not a business-service layer.

- `utils.ts`: `cn` (clsx plus tailwind-merge) and compact number formatting.
- `theme.ts`: AppTheme, stored-theme validation/default, root application, persistence.
- `agentIcons.tsx`: deterministic Lucide icon selection from agent names.

## Flow and extension

UI/layout components use `cn` to combine class values and resolve conflicting Tailwind utilities. It does not interpret arbitrary CSS-module declarations or replace CSS cascade rules. `formatCompactNumber` uses the environment locale with compact notation and at most one fractional digit; avoid tests that assume a fixed locale without controlling it.

Theme values are `dark` or `light`, defaulting to dark for invalid/missing storage or absent window. `applyTheme` sets `document.documentElement.dataset.theme` and `style.colorScheme`; `setStoredTheme` persists and applies. CSS palette definitions remain in `src/styles/tokens.css`. There is no automatic system-preference subscription in these helpers. The window/document guards do not mean localStorage access failures are caught.

`getAgentIcon` trims the name, uses its first uppercase A–Z letter to index a fixed icon list, and falls back to Bot for missing/nonalphabetic names. Keep icon selection deterministic; avoid replacing it with random choices that change on render. Inspect consumers before reordering the icon mapping.

Add a helper only for a demonstrated shared frontend concern. Keep API fetching in services, domain transformations near their domain, and React lifecycle in hooks. Reuse existing browser capabilities and dependencies rather than adding a library for one operation.

## Styling, accessibility, and verification

This directory owns no CSS. Theme application connects to plain global tokens; component visuals generally use CSS modules. Icon consumers supply accessible text or labels, and decorative icons should be hidden from assistive technology. Never communicate agent identity or state with the chosen icon alone.

No tests are colocated here. Add focused Vitest coverage when changing class merging, locale formatting, theme validation/default/application, or icon fallbacks. Use a controlled browser/storage boundary rather than assuming a DOM test harness is installed. Manually check theme persistence after reload and both themes in consuming controls. From `spa/`, run focused tests/ESLint and `yarn build` for implementation changes.
