# Embed Loader Guide

`index.ts` is the dependency-light host-page loader; it never runs chat or holds visitor credentials. `styles.ts` owns launcher icons and Shadow DOM launcher/panel CSS.

- `readOptions()` requires `data-api-key` and reads API URL, mode, target, position, look and prompt options. Script modes are floating/inline/none; `none` still mounts `[data-innomight-chat]` sections.
- `sectionOptions()` inherits the public key/look but not the script's prompt. Section prompts/labels are their own conversation context; section auto-prompt may override the inherited flag.
- Frames load `/embed/{encodedKey}#{encodedConfig}`. Floating frames warm on intent/idle and commands queue until ready; inline frames are lazy and fill caller-owned containers with a 420px minimum height.
- Incoming messages must match both frame origin and iframe window, then the shared versioned envelope. Outgoing commands target the exact API origin. Never send tokens or transcripts through this bridge.
- Preserve `window.InnomightEmbed.open/close/toggle/on`, ready callback behavior and duplicate-script protection. Inline open/close are intentionally no-ops.
- Keep mobile layout, Escape closing, focus restoration, launcher labels/expanded state and reduced-motion support. Validate configurable accent colors as `styles.ts` does; host CSS must not control Shadow DOM internals.

From `spa/`: `yarn test embed/loader` runs option/section regressions in `index.test.ts`. Build via `yarn build:embed` so loader runs after the app without deleting its assets. Manually exercise delayed readiness and multiple sections; see [embed guide](../CONTRIBUTION.md).
