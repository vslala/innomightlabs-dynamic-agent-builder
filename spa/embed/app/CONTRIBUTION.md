# Embed App Guide

`main.tsx` mounts the React app from the API shell's bootstrap and fragment config. `App.tsx` owns visitor session adoption/refresh and signed-in, guest and ended-chat screens; `useChat.ts` owns history and live reply state.

## Contracts

- `bootstrap.ts` requires `#innomight-bootstrap`; guest entry is enabled only by `allow_guests === true`. The app is served on the API origin: `api.ts` intentionally uses relative `/widget/*` URLs, not dashboard `httpClient` or a configurable foreign fetch origin.
- `WidgetApi` attaches `X-API-Key` and visitor bearer to normal requests. Auth guest/token/refresh calls use the public key plus typed bodies. Google popup messages require this iframe's origin and the actual popup source before redeeming a one-time code.
- Refresh rotates the refresh token; App deduplicates concurrent refresh and rejects results from a replaced session. Do not resurrect a session after sign-out. Guest-ended 401 is distinct from generic signed-out; guest-entry failures distinguish retryable email-check failures from policy/input failures.
- `session.ts` stores sessions by public key in iframe storage, with an in-memory fallback when blocked. Conversation selection additionally uses prompt-derived scope so sections don't steal one another's threads. Clearing a session clears all its conversation selections; guest email can be remembered separately.
- `sse.ts` parses incremental blank-line data blocks, CRLF, multiline data, malformed JSON and `[DONE]`; EOF flushes the decoder/trailing block. `useChat` accumulates response text, tool state and UI forms. This path has no dashboard turn replay/stop API; don't promise it.
- Auto-prompts wait for visibility, completed restoration and no resumed conversation; `autoPrompt: false` offers a suggestion. `promptLabel` changes display, not the submitted prompt.
- `forms.ts` serializes `<form_submission>` plus field lines; preserve compatibility with the dashboard/classic widget and backend skill parsing.

## CSS and tests

`styles.css` owns iframe chat/theme/`ie-*` presentation; components do not depend on SPA dashboard styles or loader Shadow DOM selectors. Rendering stays in `components/`, network/session logic here.

From `spa/`: `yarn test embed/app` covers API errors, session scope, SSE, forms, guest entry and delayed phases in adjacent tests. Add boundary regressions rather than mocking React internals. `yarn build:embed` bundles app then loader; follow [embed full verification](../CONTRIBUTION.md) and manually check guest expiry/end, refresh, history, section prompts and partial replies.
