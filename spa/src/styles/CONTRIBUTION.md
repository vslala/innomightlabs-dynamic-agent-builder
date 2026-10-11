# Shared Styles Contribution Guide

## Purpose and flow

`tokens.css` is the shared design-token source for the SPA and embeddable chat widget. `src/index.css` imports Tailwind and these tokens, then supplies global reset/base rules, shared utilities, keyframes, responsive-grid rules, and concierge visibility. The stylesheet here is plain global CSS, not a CSS module.

The default `:root` palette is dark. `:root[data-theme="light"]` overrides palette/surface tokens. `src/lib/theme.ts` sets the root dataset and color scheme and persists theme choice. Component styles consume variables; do not create a second independent theme palette.

## Token layout and extension

`tokens.css` includes accent/gradient variables; text and backgrounds; nav/button colors; code/JSON/canvas colors; success/warning/danger; semantic surfaces/borders/links; spacing/radii; control heights/paddings; and page/section/card/dialog/form/field spacing aliases.

Prefer semantic tokens such as `--surface-panel`, `--surface-control`, `--text-secondary`, and `--border-default` to a literal color or white-opacity utility. Use shared `--space-*` and radius/control tokens for reusable geometry; prefer the established 4/8/12/16/24/32px spacing rhythm for new layout. Existing legacy names such as `--gradient-start` have active consumers; do not rename them without finding those consumers, including embed code. Gradient-named values do not require every control to use a gradient.

For a genuinely new shared semantic role, define its dark/default and light values together; use aliases where the meaning already exists. Keep one-off component geometry in its local stylesheet. Do not put component selectors in the token file or duplicate the widget palette elsewhere.

## Modules versus global CSS

Shared controls and most components use imported `.module.css` objects with scoped classes. Modules can use Tailwind v4 `@reference "tailwindcss"` plus `@apply`, as `components/ui/button.module.css` does, or ordinary CSS. Existing dashboard and substantial page styles may use plain `.css`; those classes are global and need semantic prefixes. Follow the neighboring implementation; a plain CSS import does not provide a `styles` object. Keep broad element resets/global helpers in the existing global boundary rather than leaking them from new component stylesheets. Inline styles should generally be limited to dynamic values; some primitives deliberately merge token-based inline defaults with caller overrides.

## Verification

There are no token unit tests here. For token changes inspect both the SPA and embed consumers, both themes, focus rings, text/placeholder contrast, disabled/selected states, errors, popovers, code/JSON views, and responsive spacing. Never rely on color alone to communicate a state. Check reduced-motion behavior when changing animation utilities. From `spa/`, use `yarn build` for CSS processing/type integration and `yarn design:audit` for primitive usage; neither proves contrast or visual correctness. If embed appearance is affected, follow its own guide and build/visual checks as well.
