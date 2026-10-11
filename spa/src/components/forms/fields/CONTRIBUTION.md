# Form Field Renderers Contribution Guide

## Purpose and layout

Individual settings-schema inputs live here; orchestration belongs to `../SchemaForm.tsx` and dispatch to `../FormField.tsx`. Read [the forms guide](../CONTRIBUTION.md).

`TextField`, `TextAreaField`, `PasswordField`, `SelectField`, `SearchSelectField`, `ChoiceField`, `FileUploadField`, `KeyValueField`, and `DefaultField` cover the current input kinds. `SmartValueTextField` handles opt-in single/multiline token editing. `index.ts` exports the renderers. Specialized choice/upload/textarea/smart-value visuals have matching CSS modules; several simple fields have no stylesheet.

## Value flow and contracts

Renderers receive `field: FormInput`, `value: FormValue`, and `onChange`; `SmartValueTextField` additionally accepts `multiline`. Narrow the value before use: `FormValue` includes strings, FileList/File arrays, key-value records, and null. Emit the expected typed value, not a DOM event or serialized JSON blob.

- `TextField` sets id/name to `field.name`, uses schema placeholders/type/min/max, and recognizes email validation and multiple-email input. Browser affordances do not replace API validation.
- Choice/select/search fields use labeled options or legacy `values`. `ChoiceField` emits one string; do not copy chat's comma-separated checkbox answers here.
- `SearchSelectField` filters loaded labels and values locally. It is a custom popup, not a server-backed search or a full Radix select; inspect its keyboard and dismissal behavior before extending it.
- `FileUploadField` emits the browser FileList and shows read-only attachment chips. It reads `accept` and string-valued `multiple` attributes; it does not perform chat attachment text/Excel conversion. Upload serialization belongs to the submitting caller.
- `KeyValueField` edits row state, trims keys, discards blank keys, and produces a record (duplicate keys follow `Object.fromEntries` behavior). Its local rows reset on field-name changes, not arbitrary value changes.
- `SmartValueTextField` detects an open `{{` query, inserts complete tokens at the selection, restores the caret, and registers the focused target with its optional provider. Arrow keys select suggestions, Enter/Tab inserts, Escape closes. Without a provider it renders an ordinary input/textarea.

## Adding a field

Coordinate the backend schema and `src/types/form.ts`, add the renderer/export, update `FormField` dispatch, and consider `ViewField` read-only display. Keep option hydration/filtering in the parent helpers. Reuse `ui` controls; do not put unrelated API fetching into a basic field. Use local `.module.css` for substantial static styling and shared color/spacing/control tokens. Do not add global selectors that leak into other forms.

Preserve id/label association with `FormFieldShell`. Repeated row controls need distinct accessible names; add/remove/reveal actions need labels and `type="button"`. Custom option groups need programmatic selection and keyboard behavior, not just a changed color. Existing controls are not a blanket accessibility guarantee.

## Verification

There are no colocated field tests yet. The nearest helper tests are `yarn test src/components/forms/optionsFilter.test.ts` from `spa/`; add regressions for new value transformations and behavior. Manually test empty/initial/changed values, keyboard-only choices/search/tokens, caret insertion, missing token catalog, preview failure, upload selection, key-value blank/duplicate rows, label association, mobile layout, and both themes. For code changes run focused ESLint, `yarn build`, and `yarn design:audit`.
