# Shared UI Contribution Guide

## Purpose and layout

`src/components/ui/` is the reusable control and presentation layer. Read `../CONTRIBUTION.md` and `spa/SKILLS.md`. Files use kebab-case names; most have matching `.module.css`. `index.ts` exports many primitives, but not every local file: inspect it before relying on a barrel import.

- Controls: `button`, `link-button`, `input`, `textarea`, `search-input`, `file-input`, `checkbox`, `radio`, `select`, `switch` (an on/off setting with a sliding knob), `toggle` (a pressable chip that holds its own label), `tabs`, and `label`.
- Composition: `card`, `dialog`, `confirmation-dialog`, `accordion-panel`, expandable/icon cards, `grid`, `scroll-area`, and `separator`.
- Display and feedback: avatars, pills, status badges, stats, alerts, spinners, progress, empty states, list rows, Markdown/JSON viewers, read-only content, and step inspector.

## Flow and extension

Consumers supply values, callbacks, children, and HTML props; primitives should not fetch domain data. `Button` uses CVA to select CSS-module variants and sizes, forwards its ref and native props, and supports Radix `Slot` through `asChild`. It does not impose `type="button"`: specify the type at form call sites. For navigation use a real link, including an `asChild` link where appropriate; do not nest interactive elements.

`dialog.tsx` wraps Radix root/trigger/portal/overlay/content/title/description/close and adds layout pieces. Select, tabs, tooltip, avatar, and other wrappers also use existing Radix packages where implemented; do not assume every control is Radix-based. Preserve underlying props, refs, state attributes, and keyboard behavior when extending a wrapper. Add a small variant to an existing primitive when the behavior is genuinely shared; keep business-specific UI outside this module. Export a new shared primitive in `index.ts` if it is intended for barrel consumers.

## Styling and accessibility

CSS modules often use Tailwind v4 `@reference "tailwindcss"` and `@apply`; other styles can be ordinary module CSS. `cn` in `src/lib/utils.ts` combines class values and merges Tailwind utilities; it does not resolve conflicting declarations between arbitrary CSS-module classes. Use the shared token vocabulary for surfaces, text, focus, spacing, radii, and control sizes. Some wrappers apply token-backed inline defaults and then caller styles; check both the stylesheet and style merge before changing dimensions.

Keep focus-visible and disabled states. Dialog consumers need a meaningful title and appropriate description; preserve focus trapping, Escape, and focus return. Inputs need programmatic labels, icon-only buttons need accessible names, and selected/error states must not rely on color alone. A tooltip or placeholder alone is not an input label. Keep HTML semantics when changing `asChild`, row actions, and nested controls.

## Mermaid diagrams

Use `MermaidDiagram({ source, pending?, className?, label? })` and its shared CSS module; Markdown consumers use `MermaidMarkdownPre` at the whole `pre` boundary. Pass the live stream flag through: diagrams wait for the full response, not just a closed fence. Keep official themes, serialized rendering, stale-result/unique-ID guards and conservative source validation in the shared runtime; do not add direct Mermaid value imports to application graphs. See [Mermaid chat diagrams](../../../../docs/LLD-mermaid-chat-diagrams.md) for the build/security contract and validation limits.

## Verification

Colocated Mermaid tests cover runtime logic and static Markdown integration, not browser effects. Add focused behavioral tests for new logic using the existing Vitest setup; do not assume a DOM rendering library is installed (`package.json` currently has no Testing Library dependency). Check the consuming page manually: Tab/Shift+Tab, activation keys, select/tabs navigation, dialog Escape and focus return, long content, disabled state, mobile width, and both themes. From `spa/`, run focused ESLint on touched TSX, `yarn build`, and `yarn design:audit`. Treat the audit as a raw-control inventory, not proof of accessibility.
