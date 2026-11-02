# Release Notes Guide

This directory is the shared source for public `/whats-new`, dashboard `/dashboard/whats-new`, and the Overview release summary. Do not maintain separate release lists for these surfaces.

## Layout and flow

`whatsNewData.ts` defines typed `ChangeLogEntry`/`ChangeItem` data and `ChangeCategory` (`new`, `improved`, `fixed`). `changeLogEntries` drives rendering; `releaseMonths`, `monthAnchor`, and `totalChanges` derive navigation/counts from it.

`ReleaseNotes.tsx` renders date/category cards and month anchors with shared Card/Pill primitives. `WhatsNew.tsx` wraps them in DocsLayout and supplies release-month navigation. Dashboard `../dashboard/WhatsNewPage.tsx` reuses ReleaseNotes; `../dashboard/Overview.tsx` consumes the same entries for its summary.

## Adding an entry

Add a dated, user-facing entry in `whatsNewData.ts`, following existing newest-first ordering and category types. Group related outcomes and describe what users can now do, not commits, internal refactors, or infrastructure trivia. Keep derived month navigation/counts instead of editing parallel arrays manually. Check month anchors when adding multiple entries in one month.

## Writing for readers and content agents

Release descriptions are also used as source material for social media posts. Each item should stand on its own: name the feature and affected product surface, explain what the user can do and why it matters, and include the setup path when useful. State account prerequisites, important limits, approval behavior and any action existing users need to take. Prefer concrete workflows over vague claims such as "better integrations" or "improved experience".

Verify claims against the implementation, not just commit titles or proposed designs. Distinguish a new capability from a fix to an existing one. Do not turn committed support, app shells or planned features into claims of deployment, app-store availability or completed provider review. Keep availability caveats in the same description as the capability so an excerpt does not lose them. Preserve accurate prices, billing periods and the distinction between platform fees and AI-provider usage charges.

Historical notes may describe earlier UI (for example separate trigger management); current product instructions belong in docs, so do not treat old entries as current implementation specifications.

## Styling and verification

There are no local CSS files here. ReleaseNotes uses shared UI plus utility/inline layout; public shell styling belongs to DocsLayout and dashboard shell styling to its wrapper. New substantial styling should have a clear owner and remain usable on both surfaces.

No colocated release-note tests currently exist. Add pure tests if changing anchor/count derivation. From `spa/`: `yarn eslint src/pages/whats-new src/pages/dashboard/WhatsNewPage.tsx`, then `yarn test`, `yarn lint`, `yarn build`. Use `yarn dev` to check month/hash navigation, categories/counts, long copy, the Overview excerpt, and both public/dashboard layouts.
