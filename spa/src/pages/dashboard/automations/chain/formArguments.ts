/**
 * Bridges skill action forms to the arguments stored on a node.
 *
 * The catalog gives every action a declarative form and a JSON input schema; the
 * form speaks strings, the schema wants real types, so values are coerced on the
 * way out and stringified on the way in.
 */

import type { AutomationActionCatalogItem } from "../../../../types/automation";
import type { FormSchema, FormValue } from "../../../../types/form";

export function argumentsToFormValues(
  argumentsValue: Record<string, unknown>
): Record<string, FormValue> {
  return Object.fromEntries(
    Object.entries(argumentsValue).map(([key, value]) => {
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        return [key, value as Record<string, string>];
      }
      return [key, value == null ? "" : String(value)];
    })
  );
}

export function formValuesToArguments(
  values: Record<string, FormValue>,
  inputSchema: Record<string, unknown>
): Record<string, unknown> {
  const properties =
    typeof inputSchema.properties === "object" && inputSchema.properties !== null
      ? (inputSchema.properties as Record<string, { type?: string }>)
      : {};

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (value === null || value instanceof FileList || Array.isArray(value)) continue;
    if (typeof value === "object") {
      result[key] = value;
      continue;
    }
    // A smart value is resolved at run time, so it must survive as a string
    // even when the schema wants a number or boolean.
    if (typeof value === "string" && value.includes("{{")) {
      result[key] = value;
      continue;
    }
    const type = properties[key]?.type;
    if (type === "boolean") {
      result[key] = value === "true";
    } else if (type === "integer") {
      const parsed = Number.parseInt(String(value), 10);
      if (Number.isFinite(parsed)) result[key] = parsed;
    } else if (type === "number") {
      const parsed = Number.parseFloat(String(value));
      if (Number.isFinite(parsed)) result[key] = parsed;
    } else if (value !== "") {
      result[key] = value;
    }
  }
  return result;
}

/**
 * Any text parameter of an automation step can hold a smart value, so opt every
 * text field into the `{{` picker without each skill having to declare it.
 */
export function withSmartValues(schema: FormSchema): FormSchema {
  return {
    ...schema,
    form_inputs: schema.form_inputs.map((field) =>
      field.input_type === "text" || field.input_type === "text_area"
        ? { ...field, attr: { ...(field.attr ?? {}), smart_values: "true" } }
        : field
    ),
  };
}

export function actionFormFor(item: AutomationActionCatalogItem): FormSchema | null {
  return item.action_form ? withSmartValues(item.action_form) : null;
}
