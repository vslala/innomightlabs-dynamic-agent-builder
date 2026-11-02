# IAM Service Contribution Guide

`index.ts` owns `iamService` and explicit contracts: `IamCapabilities`, `IamMember`, `PolicyRef`, `IamGroup`, `PolicySummary`, `EffectivePolicy`, and the access summary (`ServiceAccess`, `ActionAccess`, `Reach`).

- `GET /iam/capabilities` returns `can_list_members`, `can_invite`, `can_view_permissions` (`iam:ListPolicies`) and `can_manage_permissions` (`iam:AttachPolicies`), evaluated by backend IAM for the active account.
- `getMember`, `memberAccess`, `listPolicies`, `listGroups` and `effectivePolicies(userId)` read; `attachPolicy` / `detachPolicy(userId, policy)` write `PUT/DELETE /iam/members/{id}/policies/{policy}`. Path parts are encoded (custom policies are `custom:{id}`). A refused grant keeps the API's message (`ESCALATION`, `ACCOUNT_OWNER`).
- `GET /iam/members` returns the directory and membership metadata. Call it only when listing is allowed; invitation-only permission is not directory permission.
- Both calls use the shared `httpClient`, including bearer and `X-Account-Id` headers and response/error handling. They accept an AbortSignal for page cleanup.
- `errors.ts` owns `iamErrorMessage` (the API's message, plus what to do next for refusals a person can act on) and `iamErrorCode`, for every IAM page including invitations.
- `invitations.ts` owns typed create/list/resend/revoke, public preview and authenticated acceptance. All transport uses `httpClient`; its structured `HttpError.detail` is narrowed into domain errors. A delivery-failed 502 preserves `invite_id` so the page reloads the persisted row.
- Preview and acceptance send tokens only as POST bodies. Never log them or move them into request URLs. Only preview skips auth; acceptance opts out of a 401 redirect so the page can offer invite-aware sign-in after auth is cleared.
- Writes are authorized independently by the API; capability flags are UI affordances, not proof of authorization. No client-side policy evaluator or CSS belongs here.

From `spa/`, `yarn test src/services/iam src/pages/dashboard/iam` covers the HTTP boundary and capability-gated loading. Follow the parent services guide for full validation.
