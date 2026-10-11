# Schema Forms Contribution Guide

## Purpose and layout

This module renders backend-owned form schemas for editing and viewing. Contracts live in `src/types/form.ts`; backend validation remains authoritative. Read [fields/CONTRIBUTION.md](fields/CONTRIBUTION.md) before changing individual input renderers.

- `SchemaForm`: form state and submit/change/cancel callbacks.
- `FormField`: lightweight `input_type` dispatch; `FormFieldShell`: label/help/layout.
- `fields/`: controlled input implementations and barrel exports.
- `SchemaView`, `ViewField`: read-only schema presentation.
- `useHydratedFormSchema`: option loading; `optionsFilter`: group filtering and dependent-value clearing.
- `SmartValueContext`, `SmartValueProvider`, `smartValueTokens`: opt-in template catalog and focused insertion target.
- `SmartSuggestionControl`: schema-enabled suggestion interaction.
- `index.ts`: public exports.

## Data flow

A caller fetches a `FormSchema`, passes initial values and callbacks to `SchemaForm`, and owns the actual API submission. `SchemaForm` hydrates options, initializes state from inputs, passes filtered fields into `FormField`, and calls `onSubmit(formData)`. It does not automatically post to `schema.submit_path` or display all API validation errors.

Initialization runs once: schema/initial-value changes do not imply a full state reset. File fields initialize to files/null, key-value fields to objects, and other inputs to strings/defaults. Preserve or deliberately test these lifecycle semantics when changing initialization. Submit loading comes from caller `isLoading` plus option hydration; hiding actions does not change the form's submission contract.

Hydration currently supports only the `agents` source, using `agentApiService.listAgents`; explicit nonempty options take precedence. It recognizes `options_source.type` and legacy `attr.source`. The existence of `endpoint` and `mode` in the type is not a generic endpoint loader. Requested sources are tracked to avoid repeated requests; a failed source is retried by remount, not on every render.

`withFilteredOptions` retains ungrouped options and options matching the controlling field. `applyFieldChange` clears dependent fields when the controller actually changes. Keep these rules aligned with the backend rather than adding independent provider/model validation.

Smart-value editing is enabled by `attr.smart_values === "true"`; picker/catalog behavior requires a `SmartValueProvider` above the form. The provider supplies groups, optional server-backed preview, and the last-focused insertion target. Smart suggestions are a separate schema feature; do not conflate them with template tokens.

## Extension, CSS, and accessibility

For a new backend input kind, coordinate `FormInputType`, dispatch, field export/implementation, and read-only rendering. Do not create a bespoke settings form for an interaction already described by the schema. Submit typed values unchanged except upload transport: callers use FormData and `httpClient.postForm()` where needed. Security, credentials, and allowlist decisions belong in the API.

Compose existing `ui` controls and `layout` wrappers. Forms do not have one global stylesheet; specialized fields use CSS modules and some older pieces use utilities/inline styles. Use shared tokens. `FormFieldShell` labels `field.name`; a renderer must preserve a matching id or otherwise provide a real accessible label. Help text is rendered but is not automatically connected through `aria-describedby`. Check custom choice/search controls rather than assuming the shell makes every field accessible.

## Verification

From `spa/`, run `yarn test src/components/forms/optionsFilter.test.ts`. Add focused regressions for filtering/reset and new token/value transforms. Manually check initial defaults, hydration success/failure, controller changes, uploads, API errors at the caller, cancel versus submit, and opt-in smart values with and without a provider. Check keyboard focus, label association, both themes, and long field values. For implementation changes run focused ESLint, `yarn build`, and `yarn design:audit`.
