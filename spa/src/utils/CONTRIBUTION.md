# Domain Utilities Contribution Guide

## Purpose and layout

These are small non-React functions. Keep helpers near the domain unless reuse or a nontrivial transformation justifies sharing.

- `conversations.ts`: detects automation conversations and filters them from user-visible lists.
- `time.ts`: relative-time display using Intl.RelativeTimeFormat.
- `crypto.ts`: browser AES-GCM encode/decode helpers with a fixed frontend key.

## Behavior and extension

Automation detection accepts `conversation_type === "automation"`, automation/run ids, or the legacy title prefix `Automation Run:`. Preserve compatibility deliberately when changing filtering; removing a fallback can expose run transcripts in ordinary conversation lists. `userVisibleConversations` returns a filtered array without mutating the input.

`formatRelativeTime` compares a date string against Date.now, uses descending year/month/week/day/hour/minute durations, rounds the chosen difference, and returns `just now` below the smallest threshold. Month/year lengths are approximations and the locale is English. Do not describe it as a calendar-aware date library or claim explicit invalid-date handling exists.

`crypto.ts` uses Web Crypto, a random 12-byte IV, and Base64 encoding of IV plus ciphertext. The key is shipped in frontend source; this is not secure secret storage, authentication, or confidentiality from anyone who has the bundle. Do not reuse it for credentials or sensitive data, and do not copy its key as a new security design. Inspect consumers and wire compatibility before changing it.

Keep public functions typed, deterministic where practical, and narrowly named. Domain fetching belongs in services; React effects belong in hooks/components. Use browser/standard-library capabilities and existing dependencies before adding another utility package.

## Styling, accessibility, and verification

These files have no CSS. Callers own token-based presentation and meaningful labels; a relative timestamp alone should not hide a full date needed by users.

No tests are currently colocated here. Add focused Vitest tests beside a changed helper: automation markers/fallbacks, input immutability, time thresholds/future dates with a controlled clock, and encryption roundtrip/malformed input using a suitable Web Crypto environment. Do not use roundtrip success as proof of security. From `spa/`, run the new focused test file, focused ESLint, and `yarn build` for code changes.
