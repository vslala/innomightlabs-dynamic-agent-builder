# Blueprints Page Guide

`BlueprintsPage.tsx` owns `/dashboard/blueprints`: edit blueprint YAML, validate it, fill schema-described parameters, preview a plan, apply it, and inspect deployment history. The page delegates parsing/planning/application to `blueprintApiService` in `src/services/blueprints/BlueprintApiService.ts`.

## Layout and flow

The page loads an example and previous deployments. Validation returns issues and parameter schema; SchemaForm values become params, planning previews changes, and apply returns a deployment. `blueprintView.ts` converts FormValues to string params, formats issue locations, maps deployment statuses, and links resulting resources. `blueprintView.test.ts` covers these pure view transformations.

Keep plan and apply feedback distinct. A local editor change must not be presented as already deployed, and backend diagnostics should retain their location/hint. Resource links should use existing dashboard routes; don't invent a generic resource route. This page is different from Build's conversational kit workflow, although Build reuses `DEPLOYMENT_STATUS`.

## Extension and CSS

Extend service response types before rendering new issue/resource/status kinds. Keep backend-owned YAML validation and parameter schemas at the boundary; don't add a competing YAML interpreter in the page. Add view transformations and tests in `blueprintView.ts` when reusable, leaving orchestration in the page.

`BlueprintsPage.module.css` owns editor/columns/issues/plan presentation. Preserve scoped classes, shared panels/buttons/SchemaForm, readable long diagnostics, and responsive column collapse.

## Verification

From `spa/`: `yarn test src/pages/dashboard/blueprints/blueprintView.test.ts`, `yarn eslint src/pages/dashboard/blueprints`, then `yarn test`, `yarn lint`, `yarn build`. Manually check malformed YAML, required params, failed plan/apply, deployment history, and resource links. Applying is a real mutation; use a suitable development account rather than production resources for workflow checks.
