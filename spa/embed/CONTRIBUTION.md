# Embed Widget Guide

`embed/` is the iframe-based customer chat widget, distinct from the older host-page `../widget/`. Read `AGENTS.md` and the SPA guidance before changing it.

## Layout and boundaries

| Area | Responsibility |
| --- | --- |
| `loader/` | Host-page `embed.js`: script/section attributes, launcher, iframe placement and public controls |
| `shared/protocol.ts` | Fragment configuration and versioned postMessage envelopes |
| `app/` | React chat on the API-served `/embed/{public_key}` shell; relative `/widget/*` requests |
| `app/components/` | Iframe-local presentation, Markdown, composer and agent forms |
| `test/` | Manual host/iframe/shop fixtures, not an automated test suite |

The host passes public configuration in the URL fragment; visitor tokens never belong in the loader or postMessage protocol. The app reads `#innomight-bootstrap` from the API shell. Backend origin/key/guest policy remains authoritative. Dashboard `auth_token`, active-account headers and HTTP-client redirects are not part of this visitor transport.

CSS has two owners: loader launcher/panel styles in its Shadow DOM, and `app/styles.css` inside the iframe. Host-page or dashboard CSS must not be required for chat rendering. Shared stream planning is presentation-neutral and does not own SSE parsing or CSS.

## Build and verification

From `spa/` (scripts verified in `package.json`):

```bash
yarn test embed
yarn build:embed
yarn preview:embed
```

`build:embed` builds the app first (clears `embed/dist`), then the loader (preserves it). Fixed CDN outputs are `embed/dist/embed/app.js`, `embed/app.css` and `embed/dist/embed.js`; the API shell depends on those names. Preview uses port 4174 and serves built artifacts, so rebuild after changes. The embed script is Vite-only, unlike `yarn build` (`tsc -b && vite build`); don't describe it as a TypeScript check.

For implementation work, run focused tests, then `yarn test` and `yarn lint` from `spa/`, plus embed build. Manually verify floating/inline/section chats, popup auth, guests, responsive/focus states and blocked storage with the test fixtures and a key allowing the host origin. This guide lists commands, not successful run results; infrastructure deployment is outside this module's build command.
