# Builder Service Guide

`BuilderApiService.ts` handles Ila's session schema/list/create and Connect requests. `ila.ts` is the single source for Ila identity and chat routing; `connect.ts` interprets OAuth popup messages.

- Session creation uses backend provider/model fields and `/builder/session-form`; a builder conversation can reference the kit it built or changed.
- `chatPath()` routes Ila to `/builder/{conversationId}` and ordinary agents to `/agents/{agentId}/{conversationId}`. Reuse it for send/turn paths rather than duplicating special-case IDs.
- Connect POSTs `{ provider }` to `/builder/{conversationId}/connect`; `authorize_url: null` means already connected. Popup/UI orchestration is outside the service.
- `connectOutcome()` validates the expected own origin and `innomight:oauth` data contract. A connected display message is not proof that credentials are valid; the API rechecks the connection.

From `spa/`: `yarn test src/services/builder` runs `connect.test.ts` and `ila.test.ts`. Add session transport coverage when changing the REST contract. Full checks: [services guide](../CONTRIBUTION.md).
