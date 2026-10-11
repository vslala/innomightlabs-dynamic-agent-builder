# Kits Service Guide

`KitApiService.ts` owns kit list/detail and preview-then-confirm rollback/removal. Issues and deployment statuses reuse the blueprint contract.

- Kit metadata includes owner/shared/admin access, held resources and versions. Access labels support presentation; backend permissions still decide mutations.
- `planRollback()` POSTs `{ version }` to `/kits/{id}/rollback/plan`; `rollback()` must submit the chosen version and returned `plan_id` to `/rollback`.
- Removal similarly has `/removal/plan` then `/remove` with `{ plan_id }`. Keep the plan ID intact: application must correspond to the plan the person reviewed, not an unconfirmed newly computed plan.
- Apply methods return void; plans retain create/update/unchanged/remove step distinctions. Do not silently treat removed kits as active.

From `spa/`: `yarn test src/services/kits` runs `KitApiService.test.ts`. Extend it for plan-ID/payload regressions. Full checks: [services guide](../CONTRIBUTION.md).
