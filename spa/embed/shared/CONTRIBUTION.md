# Embed Protocol Guide

`protocol.ts` is the one loader/iframe contract; both sides import it. Keep it independent of DOM rendering, API clients, CSS and session storage.

- Envelope discriminator is `source: "innomight-embed"`, `v: 1`. Host-to-frame commands are open/close; frame-to-host messages are ready/close. `isEmbedMessage()` checks discriminator/version/type shape, not the complete message union or sender identity.
- Sender checks belong at listeners: loader checks iframe source + API origin; app checks parent source. App posts non-private ready/close events to `*` because parent origin isn't known and the API shell's frame-ancestor policy controls embedding. Do not put credentials or private payloads in those messages.
- Config travels as URI-encoded JSON in the fragment, not a server query. `decodeConfig()` defaults malformed/missing config to floating/auto and normalizes mode/theme; it is not a security validator for every optional field.
- Script-only `none` is not an `EmbedMode`; mounted sections still use inline. Prompt, display label and `autoPrompt` must retain their distinct meanings across loader and app.

From `spa/`: `yarn test embed/shared` runs `protocol.test.ts`; also `yarn test embed` for both consumers. Add malformed fragments, defaults, round-trip and rejected-envelope regressions for protocol changes. Build both sides with `yarn build:embed`; see [embed guide](../CONTRIBUTION.md).
