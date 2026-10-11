# IAM Service Contribution Guide

`index.ts` owns `iamService` and explicit `IamCapabilities` / `IamMember` contracts.

- `GET /iam/capabilities` returns `can_list_members` and `can_invite`, evaluated by backend IAM for the active account.
- `GET /iam/members` returns the directory and membership metadata. Call it only when listing is allowed; invitation-only permission is not directory permission.
- Both calls use the shared `httpClient`, including bearer and `X-Account-Id` headers and response/error handling. They accept an AbortSignal for page cleanup.
- No invitation write, token handling, client-side policy evaluation or CSS belongs here in Phase 1. Future writes must be authorized independently by the API; these flags are UI affordances, not proof of authorization.

From `spa/`, `yarn test src/services/iam src/pages/dashboard/iam` covers the HTTP boundary and capability-gated loading. Follow the parent services guide for full validation.
