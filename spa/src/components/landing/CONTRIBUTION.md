# Landing Demo Contribution Guide

## Purpose and layout

This directory contains the scripted Ila illustration, not the real builder runtime. `IlaDemo.tsx` renders it; `IlaDemo.module.css` styles/animates it; `ilaScenes.ts` owns scenario data, timing, beats, and frame derivation; `ilaScenes.test.ts` protects sequencing. Other public components such as Hero and Features remain in the parent directory.

## Flow and extension

IlaDemo selects a scenario and beat, derives a frame with `beatsFor`/`frameAt`, and advances with a cleaned-up timeout. IntersectionObserver pauses advancement when the demo is offscreen. A media-query subscription tracks reduced motion; that mode renders the completed first scenario using `finalFrame`, instead of animating. Typed text uses cleaned-up delay/interval timers and an invisible full-text layer to keep the final bubble size stable.

Add or revise scenario content in `ilaScenes.ts`; keep the renderer driven by frames rather than scattering extra timer/state transitions through JSX. Preserve the story order: request, plan, approval, building, kit, website, visitor question, answer/proof. This is illustrative data and must not call production agent APIs or imply an actual connection succeeded. Keep `StepKind` and the icon mapping consistent if adding a step kind. The request blink delay is paired with CSS timing; review both when changing it.

## CSS and accessibility

Use the local CSS module and shared tokens, not global marketing selectors. Check both themes, long scenario copy, stage sizes, and overflow. The visual stage is `aria-hidden`; the figure caption conveys the story to assistive technology. Preserve a useful caption and reduced-motion final frame. The apparent approval and widget controls are illustration, not actual interactive controls—do not make them focusable unless implementing real behavior with proper semantics.

## Verification

From `spa/`, run `yarn test src/components/landing/ilaScenes.test.ts`. Add regressions for frame order, approval-before-build, timing sufficient for text, and completed reduced-motion frames when changing the scene model. Manually check cycling, offscreen pause/resume, reduced-motion changes, timer cleanup, stable bubble size, mobile layout, and light/dark themes. For implementation changes run focused ESLint and `yarn build`. Pure scene tests do not verify animation or IntersectionObserver behavior.
