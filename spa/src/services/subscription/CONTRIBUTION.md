# Waitlist Subscription Service Guide

This is the marketing waitlist, not paid Stripe subscriptions. `ISubscriptionService` exposes subscribe/list/check; `index.ts` selects the implementation.

- Only `VITE_SUBSCRIPTION_BACKEND=api` selects `ApiSubscriptionService`; the default is `LocalStorageSubscriptionService`. Keep the exported factory and singleton consistent.
- API mode uses direct fetch on `/api/waitlist/subscribe`, `/subscribers` and `/check`, not dashboard `httpClient`. It therefore does not attach dashboard bearer/account context or inherit refresh/redirect handling.
- API subscribe/check normalize email to lowercase/trimmed form; check URL-encodes the normalized email. Preserve the `SubscribeResult` contract rather than throwing away duplicate/failure outcomes.
- Local mode encrypts serialized subscriber data with `src/utils/crypto` in browser localStorage. It is local persistence, not a shared subscriber database or proof of access control. Never log email lists or ciphertext as a debugging shortcut.

No adjacent tests currently. Test backend selection, normalization, duplicate behavior and malformed local storage at the relevant boundary; use `yarn test src/services/subscription` from `spa/` once added. See [services guide](../CONTRIBUTION.md).
