# Frontend Configuration Contribution Guide

## Purpose and flow

The current source configuration is `featureFlags.ts`. It exports one `as const` object evaluated from Vite build-time environment values:

- `enableDeepResearch`: enabled only outside production and only when `VITE_ENABLE_DEEP_RESEARCH` is exactly the string `"true"`.
- `showToolActivity`: enabled unless `VITE_SHOW_TOOL_ACTIVITY` is exactly `"false"`; unset retains the existing behavior.

`enabled` and `notDisabled` deliberately encode different default policies. This is not a runtime configuration server, permission system, or secret store.

## Extension conventions

Add a flag only when a real deployment/UX requirement needs one. Define its default and exact string interpretation here rather than scattering environment comparisons across consumers. Keep the production guard if the capability must remain unavailable in production. Verify actual call sites before changing a name or default; hidden UI does not prevent API invocation.

Vite `VITE_*` values are exposed in browser bundles: never place credentials or sensitive values here. Frontend build-time flags are separate from backend settings in `api/src/config/settings.py`. When adding environment inputs, document/configure the relevant frontend build environment; a backend deploy variable alone will not change a built SPA.

## UI and verification

Configuration has no CSS. Consumers should use shared UI primitives and design tokens, and retain understandable keyboard-accessible controls when a flag is enabled or disabled. Do not use a styling condition as authorization.

No config tests are colocated here. Add focused tests for unset/true/false/other-string values and production gating if extracting or changing flag logic. Manually check tool activity and research controls under the intended Vite mode; changing an env value needs a new build/dev-process evaluation. From `spa/`, run focused ESLint and `yarn build` for code changes. Do not claim a production-only branch was verified by a dev-mode visual check.
