# Chat Service Guide

`ChatService.ts` owns dashboard message/image transport and replayable turn streams. UI rendering/state and SSE event types live outside this service.

## Contracts

- Direct fetch uses the configured API base plus `authHeaders()` (bearer and `X-Account-Id`). It does not run HTTP-client token-refresh, login-redirect or rate-limit interception; preserve this distinction when handling failures.
- `sendMessage(agentId, conversationId, message: OutgoingMessage, options)` uses `chatPath()` for Ila/agent routing. `sendMessageBody()` builds the request with only the parts the message has (attachments, `image_ids`, `references`, `deep_research`). Image generation remains on agent-specific paths.
- `X-Turn-Id` reaches `onTurnStarted` before events. A 409 with `detail.turn_id` reaches `onConflict` when supplied: attach rather than resend and create duplicate work.
- Abort cancels the browser read, not the detached backend turn. Explicit `stopTurn()` POST stops it; 404 there is accepted as already finished.
- `followTurn()` uses `after_sequence`, up to three attempts with increasing delays. 410 invokes completion so consumers can reload persisted messages. EOF invokes completion too; it is not itself proof of successful agent execution.
- SSE parsing accumulates decoded chunks, consumes blank-line blocks, tracks `id:` and parses `data:` JSON. Preserve processing of a final block without a trailing separator. Aborts are silent; other stream failures reach `onError`.

## Verification

No adjacent tests currently. Add stream-boundary regressions using mocked fetch/ReadableStream: split JSON/UTF-8, final unterminated block, conflicts, 410, abort versus stop and account headers. From `spa/`, run `yarn test src/services/chat` once tests exist; then [services full checks](../CONTRIBUTION.md). Do not reuse the widget SSE parser blindly: its transport and event contract differ.
