# Auth Route Wrapper Contribution Guide

## Purpose and flow

This directory currently contains only `ProtectedRoute.tsx`. It gates rendering of signed-in children, using `authService` from `src/services/auth`; login pages, token storage, and HTTP refresh behavior are not implemented here.

On mount the wrapper checks for a token. Missing tokens finish validation as unauthenticated. Whether the local token appears expired or valid, an existing token is checked with `authService.getCurrentUser()`; this also allows the service/backend refresh path to run. Failure removes the token. While waiting, a session-validation screen renders; unauthenticated users are redirected to `/` with `replace` and `state={{ from: location }}`. Authenticated children render unchanged. The effect is mount-based, not a subscription to every token or route change.

## Extension and presentation

Keep token parsing/storage and transport in the auth/HTTP services. Preserve loading-before-children behavior and intended-destination state when changing redirects. A client wrapper is not authorization: API access checks remain necessary. Do not implement a second refresh mechanism in this component.

The current loading screen uses utility classes and shared token colors, with no local CSS file. New substantial static styling can use a CSS module; do not introduce global auth selectors or literal dark-only colors. Ensure status is understandable without the spinner and keyboard/screen-reader users can identify the loading or redirect outcome. Use shared `ui` feedback primitives where appropriate.

## Verification

No auth-wrapper tests are colocated here. Add focused tests for absent token, valid token, refreshable expired token, backend rejection/removal, destination preservation, and preventing protected-child flashes; mock the external auth boundary rather than inventing token semantics. The current dependencies do not include a DOM-testing library. Manually exercise sign-in, expired session, failed validation, and direct dashboard navigation. From `spa/`, run focused ESLint and `yarn build` for implementation changes; check both themes for loading presentation.
