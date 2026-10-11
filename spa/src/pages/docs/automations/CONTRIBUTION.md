# Automation Documentation Sandbox Guide

This module embeds the real dashboard `AutomationWorkspace` in public `/docs/automations` without running production automations. Read the dashboard automations guides before changing shared interfaces.

## Layout and flow

`AutomationSandbox.tsx` selects tutorial stage/expanded step, adds reset affordances, and renders the workspace. `tutorialFixtures.ts` supplies created/agent/email/scheduled graphs, sample agent/recipient, action catalog, trigger forms, install schema, and simulated action outputs.

`useSandboxAutomation.ts` supplies compatible `AutomationDraft`, `AutomationRunsState`, `WorkspaceParams`, `WorkspaceOperations`, and `ChainGateway` values. It uses the same linearization/mutations/validation/condition/path helpers as the dashboard while handling edits, trigger setup, smart-value previews, and staged run results locally. This boundary is why cards must not import production services directly.

## Extension and safety

Add a tutorial stage/interaction to fixtures first, then its local adapter behavior and documentation use in `../Automations.tsx`. Keep sample aliases/output shapes consistent so smart-value examples resolve. Changing a workspace prop, gateway method, or returned hook interface requires updating the sandbox adapter too.

Keep execution visibly simulated. Do not introduce credential collection, real connector authorization, production API mutations, or email sends into a signed-out tutorial. Reset must restore the intended stage, selections, and run state; clean up simulated timing when unmounted/reset.

## CSS and verification

`AutomationSandbox.module.css` owns wrapper/toolbar/frame/caption. The embedded workspace imports dashboard `styles.css` and `workspace.css`; those global prefixed classes own chain internals. Do not copy them into the module or fork card styling unnecessarily.

No sandbox-specific tests are currently colocated. Existing pure logic tests are reused: from `spa/`, `yarn test src/pages/dashboard/automations/chain/chain.test.ts src/pages/dashboard/automations/hooks/workspaceParams.test.ts`; focus lint with `yarn eslint src/pages/docs/automations`, then run `yarn test`, `yarn lint`, `yarn build`. Manually exercise every stage, edit/branch/test/trigger interactions, reset during a simulated run, and narrow layouts.
