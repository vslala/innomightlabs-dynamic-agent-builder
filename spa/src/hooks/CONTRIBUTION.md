# Shared Hooks Contribution Guide

## Purpose and layout

This directory holds reusable React lifecycle/state logic; page-specific hooks can stay beside their page.

| File | Behavior |
| --- | --- |
| `useArtifactHtml.ts` | Gated authenticated text fetch; loading/loaded/failed discriminated state |
| `useCanManageSettings.ts` | Settings-control visibility through SettingsAccessService |
| `useFileAttachments.ts` | Chat attachment validation, reading, Excel conversion, and state |

## Flow and extension

`useArtifactHtml(contentUrl, enabled)` waits for a URL and enabled flag, resets to loading when fetching, and calls fetch with `authHeaders()`. It suppresses stale state updates with an active flag on cleanup, but does not abort the request. Consumers supply backend content-proxy URLs; do not pass arbitrary third-party URLs that would receive auth headers. HTML sandboxing belongs to the canvas consumer, not this hook. This direct authenticated raw-text fetch is an existing exception to the normal service/httpClient path.

`useCanManageSettings()` returns undefined while loading, the API's `can_manage` on success, and true on lookup failure. That fail-open behavior only exposes controls; it is not permission enforcement. The API must still authorize mutations.

`useFileAttachments()` exposes attachments, error, add/remove/clear operations, and total size. It uses limits/extensions from `src/types/message.ts`, rejects duplicate display filenames, reads text via FileReader, and converts Excel sheets to CSV using the existing xlsx dependency. Multiple sheets get separators; converted names end in `.csv`. Stored size is `content.length`, while admission checks use file sizes—do not describe this as exact post-conversion byte accounting. These chat text attachments are different from schema-form binary uploads.

Keep domain network work in services by default; extract a hook only for genuine reusable React state/lifecycle behavior. Respect effect dependencies, cleanup, and concurrent/unmounted completion; do not invent a global cache for a one-page interaction.

## Presentation and verification

Hooks have no CSS; consumers own UI, error messaging, focus, accessible loading states, and token-based styles. Do not import styles into a nonvisual hook.

There are no colocated hook tests yet. Add focused tests for gates/stale completions, permission lookup failure, attachment counts/extensions/sizes, duplicates after Excel renaming, read failures, and clear/remove behavior when changing them. Mock real browser/network boundaries (fetch, FileReader) deliberately; the current package does not include a DOM hook-testing library. Manually check lazy canvases, failed loads, settings visibility, and upload selection/removal in consuming pages. From `spa/`, run focused ESLint and `yarn build` for implementation changes.
