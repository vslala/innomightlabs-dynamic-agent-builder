# Automation Marketplace Guide

`AutomationMarketplacePage.tsx` and `AutomationMarketplaceDetail.tsx` own `/dashboard/automations/marketplace` and its `:templateId` detail route. Publishing belongs to `automations/AutomationDetailLayout.tsx`; editing the imported automation belongs to the workspace.

## Flow and boundaries

The list queries `automationMarketplaceApiService.listAutomations` with search text. Detail loads the template and import plan, renders schema-driven inputs/dependency configuration, then calls `importAutomation`. `saveImportSession` preserves import setup for continuation; detail uses `HttpError` to handle API failures. Inspect that path when changing connector/setup requirements rather than replacing backend error handling with generic success navigation.

API methods are in `src/services/automationMarketplace/AutomationMarketplaceApiService.ts`; contracts are in `src/types/automationMarketplace.ts`. Keep template IDs distinct from newly created automation IDs. Import inputs are template setup, not the runtime `input.*` test values used by the workspace.

## Extension and styling

Extend backend plan/types and SchemaForm inputs together. Preserve pending setup, missing requirements, retry feedback, and submission locking. Do not implement a second graph editor or credential form here; reuse services/schema forms and route to the real automation workspace after success.

There are no local CSS files in this directory. Both screens currently compose shared layout/UI with utility/inline styling. New substantial page layout should get semantic page-local styling; do not borrow global workspace selectors for marketplace cards.

## Verification

No colocated marketplace tests currently exist. Add focused tests for new plan/input/error transformations. From `spa/`: `yarn eslint src/pages/dashboard/automation-marketplace`, `yarn test`, `yarn lint`, `yarn build`. Manually check search, direct template URLs, missing setup/continuation, failed import, and successful workspace navigation.
