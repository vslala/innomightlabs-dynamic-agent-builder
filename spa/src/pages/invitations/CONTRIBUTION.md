# Invitation Acceptance Contribution Guide

`/invitations/accept` is public and nonindexed. It must remain reachable before the user belongs to any account; do not wrap it in dashboard membership dependencies.

## Flow and ownership

- `continuation.ts` captures/removes a fragment token, retains it only in same-tab sessionStorage, and builds OAuth links with a nonredeemable hash context. No localStorage draft or raw-token query parameters.
- `AcceptInvitationPage.tsx` previews via POST, offers Google/Cognito sign-in, and requires an explicit accept action after authentication. Backend verified-email matching is authoritative. A 401 clears auth and returns to sign-in options without abandoning the pending invitation.
- `acceptInvitation.ts` awaits membership acceptance and server account selection before clearing the token or navigating. It must not change local account context before server selection succeeds; failed selection is safely retryable.
- `loginHandoff.ts` ensures invitation continuation precedes checkout/dashboard navigation after the usual session-code redemption.
- `Invitations.module.css` owns local token-based presentation. Use shared Button and semantic headings/status/error content.

## Hosting security boundary

React cleanup is not early enough: `index.html` and `public/404.html` run synchronous bootstraps before analytics/external resources. The 404 fallback must never encode a fragment token into its redirect query. These bootstraps and this module share the `pendingInvitationToken` storage key. Keep them in sync and test the actual HTML scripts, not only helpers. Blocked storage still clears the fragment and uses a nonsecret error marker; do not fall back to an old pending token.

The acceptance route suppresses analytics initialization and SiteConcierge. The public-pages build plugin emits a noindex acceptance shell but does not put it in the sitemap. Tokens never go through OAuth; the signed callback context contains only the preview hash, and membership acceptance still requires the original token plus the verified matching identity.

## Verification

From `spa/`, run `yarn test src/pages/invitations src/services/iam src/services/http src/routes`, focused ESLint, full `yarn test` and `yarn build`. Test expired sessions, wrong-email failures, server account-switch failure, StrictMode continuation, storage failure, original and legacy 404 redirects, and secrets absent from request URLs/analytics. Inspect the emitted shell and deploy it with the updated 404 file. Browser/provider checks must separately verify Google/Cognito round trips, dark/light themes, keyboard focus and narrow layouts; unit/SSR/VM tests do not prove them.
