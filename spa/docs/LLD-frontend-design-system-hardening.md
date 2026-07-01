# Low Level Design: Frontend Design System Hardening

Date: 2026-07-01  
Status: Draft  
Owner: InnomightLabs SPA

## Summary

Harden the SPA design layer so the product renders consistently across pages, themes, dialogs, forms, cards, and action surfaces.

The immediate problem is not one broken page. The app already has shared UI components, but pages can still bypass or weaken their contracts through ad hoc Tailwind utilities, inline styles, raw HTML controls, and page-specific CSS. That is why button padding, card spacing, read-only content padding, select backgrounds, and form margins regress repeatedly.

The fix is to make the design system explicit:

- Design tokens own spacing, control size, radius, typography, and surface colors.
- Primitive components own their own visual contracts.
- Layout components own page/section/form spacing.
- Pages compose those components instead of inventing local spacing.
- Tooling catches new raw controls and common spacing overrides before they spread.

This should be implemented incrementally. Do not rewrite the full SPA in one risky pass.

## Current State Findings

Relevant files:

- `spa/src/index.css`
- `spa/src/components/ui/button.tsx`
- `spa/src/components/ui/card.tsx`
- `spa/src/components/ui/dialog.tsx`
- `spa/src/components/ui/input.tsx`
- `spa/src/components/ui/select.tsx`
- `spa/src/components/ui/textarea.tsx`
- `spa/src/components/forms/SchemaForm.tsx`
- `spa/src/components/forms/FormField.tsx`
- `spa/src/pages/dashboard/**`

The current design layer has useful foundations:

- Shared UI primitives exist under `spa/src/components/ui/`.
- Theme variables exist in `spa/src/index.css`.
- Schema-driven forms exist through `SchemaForm`.
- Most newer pages import `Button`, `Card`, `Input`, and `Select`.

The problem is contract drift:

- `Button` has component defaults, but callers still rely on page-level `className` and raw utility spacing.
- `CardHeader` and `CardContent` have defaults, but pages override padding heavily.
- `SchemaForm` has its own inline gap/action row and does not use a reusable form layout primitive.
- Some components/pages still use raw `<button>`, `<input>`, `<select>`, and `<textarea>`.
- `index.css` defines colors but not a full spacing/control/radius scale.
- Page layouts repeatedly use local `space-y-*`, `gap-*`, `p-*`, and inline spacing.
- Dialogs do not provide a standard body/footer layout with enough default internal spacing.
- Read-only surfaces are not a first-class component, so pages use `pre`, `div`, or `Card` differently.

This makes every new page responsible for spacing correctness, which defeats the purpose of a component library.

## Design Goals

- Make the default UI correct without per-page padding fixes.
- Make buttons, inputs, selects, textareas, cards, dialogs, and forms visually identical wherever used.
- Reduce raw HTML controls in product pages.
- Keep Tailwind available, but stop using utility classes as the primary design contract.
- Support dark and light themes from the same token set.
- Preserve current product behavior while migrating visuals incrementally.
- Make future pages easy to build from stable components.

## Non-Goals

- No full visual redesign of the brand in this phase.
- No migration away from React or Tailwind.
- No Storybook dependency required for v1, though a lightweight showcase route is recommended.
- No rewrite of public landing pages unless they share broken dashboard controls.
- No blocking on perfect static enforcement before the first migration.

## Architecture

Use a layered design system.

```text
Design tokens
  -> Primitive components
    -> Layout components
      -> Domain/page components
        -> Pages
```

Rules:

- Tokens are the source of truth for spacing, sizing, surfaces, and typography.
- Primitives should render correctly without caller-provided padding.
- Layout components should own section/card/form/page spacing.
- Pages should express structure and data, not micro-spacing.

## Design Tokens

Extend `spa/src/index.css` with semantic tokens.

Recommended token groups:

```css
:root {
  --space-0: 0;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;

  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;

  --control-height-sm: 2.5rem;
  --control-height-md: 2.75rem;
  --control-height-lg: 3rem;
  --control-padding-x-sm: 1rem;
  --control-padding-x-md: 1.5rem;
  --control-padding-x-lg: 2rem;

  --page-gap: var(--space-8);
  --section-gap: var(--space-6);
  --card-padding: var(--space-6);
  --card-padding-lg: var(--space-8);
  --dialog-padding: var(--space-8);
  --form-gap: var(--space-5);
  --field-gap: var(--space-2);
}
```

The existing color variables should remain, but surface variables should become more semantic over time:

- `--surface-page`
- `--surface-panel`
- `--surface-panel-hover`
- `--surface-control`
- `--surface-popover`
- `--border-default`
- `--border-strong`

Light and dark themes should define the same variables.

## Primitive Component Contracts

### Button

File: `spa/src/components/ui/button.tsx`

Contract:

- Owns height, horizontal padding, vertical padding, icon gap, font weight, radius, focus state, disabled state, and loading state.
- Supports `variant`: `default`, `outline`, `secondary`, `ghost`, `destructive`, `link`.
- Supports `size`: `sm`, `md`, `lg`, `icon`, `action`.
- Text must never touch the boundary.
- Icon-only buttons must have fixed square dimensions.
- Text buttons should grow with content and have a sane min-width only for `action`.

Implementation notes:

- Keep critical sizing in component-owned styles or CSS classes backed by tokens.
- Do not rely only on caller utility classes for padding.
- Add optional `loading` prop to avoid every page implementing loading text differently.

### Input, Select, Textarea

Files:

- `spa/src/components/ui/input.tsx`
- `spa/src/components/ui/select.tsx`
- `spa/src/components/ui/textarea.tsx`

Contract:

- Own height/padding/background/border/focus/error/disabled states.
- Dropdown content must always be opaque and above page text.
- Placeholder and selected text must have theme-safe contrast.
- Field text must not touch borders.
- Select trigger and item padding must be component-owned.

### Card and Panel

File: `spa/src/components/ui/card.tsx`

Current `Card` is useful but too generic. Keep it, and add stricter composition:

- `Panel`
- `PanelHeader`
- `PanelTitle`
- `PanelDescription`
- `PanelBody`
- `PanelFooter`

`Card` can remain as a primitive, but new dashboard pages should use `Panel` unless they need custom repeated-item cards.

Panel contract:

- Owns header/body/footer padding.
- Offers density: `default`, `compact`, `spacious`.
- Supports actions in the header without callers manually building flex/padding.

### Dialog

File: `spa/src/components/ui/dialog.tsx`

Add:

- `DialogBody`
- `DialogSection`
- `DialogActions`

Contract:

- Dialog body has default vertical rhythm.
- Forms inside dialogs should not touch each other.
- Footer spacing is stable and responsive.
- Max height scrolling should happen inside body, not by crushing padding.

### ReadOnlyContent

Add:

- `spa/src/components/ui/read-only-content.tsx`

Use this for marketplace instructions, generated report previews, raw text snippets, prompts, configs, and code-like read-only blocks.

Contract:

- Owns padding, border, background, line-height, overflow, and theme contrast.
- Supports variants:
  - `plain`
  - `code`
  - `instructions`
- Supports `selectable?: boolean`, defaulting to true. Marketplace instructions can set `selectable={false}` as UX friction, not a security control.

## Layout Components

Add under `spa/src/components/layout/` or `spa/src/components/ui/layout/`.

Recommended initial set:

### Page

```tsx
<Page>
  <PageHeader title="Agents" description="Create and manage your AI agents">
    <PageActions>...</PageActions>
  </PageHeader>
  <PageBody>...</PageBody>
</Page>
```

Owns:

- Page vertical spacing.
- Header/action alignment.
- Mobile stacking.

### Section

```tsx
<Section title="Instructions" description="Read-only template instructions">
  ...
</Section>
```

Owns:

- Section margin.
- Header/body spacing.
- Optional action slot.

### Stack

```tsx
<Stack gap="lg">...</Stack>
```

Use instead of repeated `space-y-*`.

### Inline

```tsx
<Inline gap="md" align="center" justify="between">...</Inline>
```

Use instead of repeated `flex gap-* items-* justify-*`.

### FormStack and FieldGroup

```tsx
<FormStack>
  <FieldGroup label="Agent name">
    <Input />
  </FieldGroup>
</FormStack>
```

`SchemaForm` should render through these.

### SidebarLayout

For surfaces like marketplace detail and automation builder:

```tsx
<SidebarLayout sidebar={<ImportPanel />}>
  <MainContent />
</SidebarLayout>
```

Owns:

- Grid columns.
- Responsive collapse.
- Gaps.
- Sidebar width.

## SchemaForm Hardening

File: `spa/src/components/forms/SchemaForm.tsx`

Current behavior:

- Uses inline flex/gap.
- Manually builds action row.
- Does not expose density.
- Some form fields use raw inputs in adjacent components.

Target behavior:

```tsx
<SchemaForm
  schema={schema}
  density="default"
  layout="stack"
  actions="footer"
/>
```

Recommended changes:

- Use `FormStack`.
- Use `FieldGroup` through `FormFieldShell`.
- Use `ActionRow` for submit/cancel buttons.
- Add `hideActions` for embedded config forms that should autosave or use parent-level submit.
- Add `submitMode`: `inline` or `footer`.
- Keep current props backward compatible.

## Page Migration Order

Migrate by blast radius and visible pain.

### Phase 1: Foundations

Files:

- `spa/src/index.css`
- `spa/src/components/ui/button.tsx`
- `spa/src/components/ui/input.tsx`
- `spa/src/components/ui/select.tsx`
- `spa/src/components/ui/textarea.tsx`
- `spa/src/components/ui/card.tsx`
- `spa/src/components/ui/dialog.tsx`
- `spa/src/components/forms/SchemaForm.tsx`

Add:

- `ReadOnlyContent`
- `Page`, `PageHeader`, `PageActions`, `PageBody`
- `Section`
- `Stack`
- `Inline`
- `FormStack`
- `FieldGroup`
- `ActionRow`
- `SidebarLayout`

### Phase 2: Marketplace and Agent Pages

Files:

- `spa/src/pages/dashboard/agent-marketplace/AgentMarketplacePage.tsx`
- `spa/src/pages/dashboard/agent-marketplace/MarketplaceAgentDetail.tsx`
- `spa/src/pages/dashboard/AgentsList.tsx`
- `spa/src/pages/dashboard/agent-detail/AgentOverviewPage.tsx`
- `spa/src/pages/dashboard/agent-detail/AgentSkillsPage.tsx`
- `spa/src/pages/dashboard/agent-detail/AgentMemoryPage.tsx`

Goal:

- Remove local card/dialog/button padding fixes.
- Use `Page`, `Section`, `SidebarLayout`, `ReadOnlyContent`, and `FormStack`.

### Phase 3: Automation Builder

Files:

- `spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx`
- `spa/src/pages/dashboard/automations/styles.css`
- related automation panels/forms.

Goal:

- Make light/dark theme parity reliable.
- Standardize toolbar/action buttons.
- Standardize panel padding and form spacing.
- Keep React Flow canvas styling isolated from control styling.

### Phase 4: Analytics, Knowledge, Conversations, Artifacts

Files:

- `spa/src/pages/dashboard/agent-detail/analytics/**`
- `spa/src/pages/dashboard/KnowledgeBases.tsx`
- `spa/src/pages/dashboard/KnowledgeBaseDetail.tsx`
- `spa/src/pages/dashboard/Conversations.tsx`
- `spa/src/pages/dashboard/ConversationDetail.tsx`
- `spa/src/pages/dashboard/ArtifactsPage.tsx`

Goal:

- Remove raw layouts and repeated utility spacing.
- Standardize dashboard cards and action rows.

### Phase 5: Chat and Widget Forms

Files:

- `spa/src/components/chat/ChatFormRenderer.tsx`
- `spa/src/components/chat/ChatStreamRenderer.tsx`
- `spa/src/components/ui/expandable-chat-box.tsx`

Goal:

- Replace raw form controls with primitives.
- Standardize submitted form rendering, tool activity cards, and artifact links.

## Enforcement

### ESLint / Static Checks

Add lightweight checks before introducing heavier tooling.

Recommended script:

```bash
yarn design:audit
```

It should flag:

- Raw `<button>` outside `components/ui`.
- Raw `<input>`, `<select>`, `<textarea>` outside form primitive files.
- `className` containing `px-`, `py-`, `p-`, `space-y-`, or large `gap-` in page files.
- Inline `style={{ padding... }}` in page files.

This should initially be warning-only. Once migration finishes, make it fail CI for `spa/src/pages/dashboard/**`.

### Component Review Rules

- New dashboard pages must use `Page`.
- New panels must use `Panel` or `Section`.
- New forms must use `SchemaForm` or `FormStack`.
- New buttons must use `Button`; no raw `<button>` in pages.
- No page should add padding to `Button` unless creating a deliberate new size variant.

## Design Showcase

Add a dev-only route or page:

- `spa/src/pages/dashboard/DesignSystemPage.tsx`
- Route: `/dashboard/design-system`

Show:

- Buttons by variant/size.
- Inputs/selects/textareas in normal/focus/disabled/error states.
- Cards/panels by density.
- Dialog example.
- Form example.
- ReadOnlyContent examples.
- Light and dark theme preview.

This gives visual QA a stable target instead of checking random product pages.

## Visual QA

Use Playwright or a lightweight screenshot script later.

Initial screenshot targets:

- `/dashboard/agents`
- `/dashboard/agents/marketplace`
- `/dashboard/agents/marketplace/:templateId`
- `/dashboard/agents/:agentId`
- `/dashboard/agents/:agentId/skills`
- `/dashboard/agents/:agentId/memory`
- `/dashboard/automations/:automationId`

Viewports:

- Desktop: `1440x1000`
- Tablet: `1024x900`
- Mobile: `390x844`

Themes:

- dark
- light

Checks:

- Buttons have internal padding.
- Text does not touch card borders.
- Dialog sections have clear spacing.
- Dropdowns are opaque.
- Form inputs do not collide.
- No text overflows container bounds.

## Implementation Steps

1. Add design tokens to `spa/src/index.css`.
2. Add layout primitives: `Page`, `Section`, `Stack`, `Inline`, `ActionRow`, `SidebarLayout`.
3. Add `ReadOnlyContent`.
4. Harden `Button`, `Input`, `Select`, `Textarea`, `Card`, and `Dialog` contracts.
5. Refactor `SchemaForm` to use `FormStack` and `ActionRow`.
6. Migrate marketplace and agent pages.
7. Migrate automation builder.
8. Migrate analytics, knowledge, conversations, and artifacts pages.
9. Migrate chat/widget form surfaces.
10. Add `design:audit` script in warning mode.
11. Add design-system showcase route.
12. Add screenshot QA once the first two phases are stable.

## Testing

Run on every phase:

```bash
cd spa
yarn build
```

After component migrations:

```bash
cd spa
yarn design:audit
```

If screenshot tooling is added:

```bash
cd spa
yarn test:visual
```

## Risks

- Large visual migration can create regressions if done page-by-page without a stable component contract.
- Overly strict linting too early will block useful work.
- Moving all spacing into primitives can make truly custom surfaces harder if escape hatches are not explicit.
- Inline style removal can break pages that rely on dynamic layout calculations.

Mitigation:

- First harden primitives, then migrate pages.
- Keep escape hatches through semantic props like `density`, `size`, `layout`, and `variant`.
- Start enforcement in warning mode.
- Keep each migration PR/page group small.

## Success Criteria

- Shared controls render consistently across dashboard pages.
- Button text never touches boundaries.
- Card/read-only/dialog content has stable internal padding.
- Form fields have consistent vertical spacing.
- Light and dark themes both pass visual QA.
- New pages can be composed with `Page`, `Section`, `Panel`, and `SchemaForm` without ad hoc spacing.
- `design:audit` reports no raw controls or spacing overrides in migrated dashboard pages.
