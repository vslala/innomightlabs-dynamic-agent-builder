# Services Guide

`src/services/` owns dashboard API contracts, not page state or styling. Read `../../AGENTS.md`, `../../SKILLS.md` and the relevant domain guide before changing a call.

## Boundaries

- Keep singleton services and explicit request/response types beside the domain; reuse `src/types/` where already authoritative. Export through the existing barrel when one exists; do not add a facade just for uniformity.
- Ordinary dashboard JSON requests use `http/httpClient`: API base URL, bearer token, active-account header, refreshed tokens, errors and redirects belong there. Backend IAM remains authoritative; an ID or an `access` label is not permission.
- Public pricing and downloads deliberately use `skipAuth`. This suppresses both bearer and account headers, not the client's response interception.
- `chat/` uses direct `fetch` for SSE and image requests, with `authHeaders()` for bearer/account context. It does not inherit HTTP-client refresh/redirect/error handling. `subscription/` is a separate waitlist transport with a local-storage default.
- Schema-backed flows return `FormSchema` for `SchemaForm`; pass values through rather than duplicating backend security/credential validation. Multipart uploads use `postForm`, never a manually supplied boundary.
- Services do not own CSS, React state or rendering. Keep those in consuming pages/components. Widget visitor authentication belongs in `embed/app` or `widget`, not dashboard auth.

## Verification

From `spa/`, `yarn test src/services` runs matching Vitest tests; narrow further by domain/file while working. Add boundary regressions for paths, payloads, account/auth headers and error cases. Many domains currently have no adjacent tests; a filter alone does not establish coverage.

`package.json` defines `yarn test` (`vitest run`), `yarn lint` (`eslint .`) and `yarn build` (`tsc -b && vite build`). Run focused tests then the full SPA suite and build for implementation changes. Commands here are verified from configuration, not a claim that they have passed.
