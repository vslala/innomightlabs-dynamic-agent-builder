# IAM Service Contribution Guide

`index.ts` owns `iamService` and explicit `IamCapabilities` / `IamMember` contracts.

- `GET /iam/capabilities` returns `can_list_members` and `can_invite`, evaluated by backend IAM for the active account.
- `GET /iam/members` returns the directory and membership metadata. Call it only when listing is allowed; invitation-only permission is not directory permission.
- Both calls use the shared `httpClient`, including bearer and `X-Account-Id` headers and response/error handling. They accept an AbortSignal for page cleanup.
- `invitations.ts` owns typed create/list/resend/revoke, public preview and authenticated acceptance. All transport uses `httpClient`; its structured `HttpError.detail` is narrowed into domain errors. A delivery-failed 502 preserves `invite_id` so the page reloads the persisted row.
- Preview and acceptance send tokens only as POST bodies. Never log them or move them into request URLs. Only preview skips auth; acceptance opts out of a 401 redirect so the page can offer invite-aware sign-in after auth is cleared.
- Writes are authorized independently by the API; capability flags are UI affordances, not proof of authorization. Permission presets remain Phase 3. No client-side policy evaluator or CSS belongs here.

From `spa/`, `yarn test src/services/iam src/pages/dashboard/iam` covers the HTTP boundary and capability-gated loading. Follow the parent services guide for full validation.
