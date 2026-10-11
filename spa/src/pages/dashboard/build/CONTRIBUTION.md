# Build and Kits Guide

`BuildPage.tsx` owns `/dashboard/build`, starting/resuming Ila builder sessions and listing kits. `KitDetailPage.tsx` owns `/dashboard/build/kits/:kitId`, showing resources, versions, and removal/rollback operations.

## Layout and flow

Build loads the builder session form and sessions through `builderApiService`, and kit summaries through `kitApiService`. SchemaForm chooses provider/model; creating a session leads into the conversation workflow rather than embedding another chat runtime here.

Kit detail loads kit state and requests a removal or rollback plan. `KitPlanDialog.tsx` shows that plan before confirmation; the apply request sends its `plan_id`. Keep this plan-first boundary: never apply an unseen plan or reuse a plan for a different operation/version. Reload detail after a successful mutation.

`kitView.ts` owns kind/count/status/version labels, rollback eligibility, plan action mappings, and changing-step filtering. `kitView.test.ts` protects these helpers. Deployment-status presentation is reused from `../blueprints/blueprintView.ts`. API contracts live in `src/services/kits/KitApiService.ts`; its service test covers plan-ID requests.

## Extension and CSS

Add new kit/plan kinds to explicit contracts and view mappings, with regression assertions for eligibility and visible changes. Keep access flags and destructive confirmation visible. Shared chat/connection behavior belongs to conversation components and builder services, not this page.

`BuildPage.module.css` owns sessions/kits/list layout. `KitDetailPage.module.css` owns detail and is also imported by `KitPlanDialog.tsx`. Keep plan dialog styles there unless a genuinely separate owner emerges; use theme variables and shared UI primitives.

## Verification

From `spa/`: `yarn test src/pages/dashboard/build/kitView.test.ts src/services/kits/KitApiService.test.ts`, `yarn eslint src/pages/dashboard/build`, then `yarn test`, `yarn lint`, `yarn build`. Check session navigation, missing kits, denied actions, rollback eligibility, plan cancel/confirm/error, and responsive detail/dialogs. Removal/rollback change real resources; use development fixtures/accounts.
