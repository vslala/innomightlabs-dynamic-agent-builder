import type { FormInput, FormValue } from "../../types/form";

/**
 * A field's options narrowed by its `options_filter`: only those grouped under the
 * filtering field's current value, plus ungrouped ones. The same rule as
 * `FormOptionsFilter.apply` in api/src/form_models.py, which validates the submit.
 */
export function withFilteredOptions(field: FormInput, formData: Record<string, FormValue>): FormInput {
  const filter = field.options_filter;
  if (!filter || !field.options) {
    return field;
  }
  const selected = formData[filter.field];
  return {
    ...field,
    options: field.options.filter((option) => option.group == null || option.group === selected),
  };
}

/**
 * Form data after `fieldName` changes to `value`. Fields filtered by it are cleared,
 * so a model chosen for the previous provider can't be submitted with the new one.
 */
export function applyFieldChange(
  fields: FormInput[],
  formData: Record<string, FormValue>,
  fieldName: string,
  value: FormValue
): Record<string, FormValue> {
  const next = { ...formData, [fieldName]: value };
  if (formData[fieldName] === value) {
    return next;
  }
  for (const field of fields) {
    if (field.options_filter?.field === fieldName) {
      next[field.name] = "";
    }
  }
  return next;
}
