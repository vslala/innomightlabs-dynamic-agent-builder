/**
 * Forms an agent asks the visitor to fill in (e.g. the lead capture skill).
 * Answers go back to the agent as a `<form_submission>` message in the same
 * format the classic widget and the dashboard use, so skills parse both alike.
 */

import type { AgentForm, FormInput } from "./api";

export interface FormAnswer {
  fieldId: string;
  label: string;
  value: string;
}

const NATIVE_INPUT_TYPES = { email: "email", phone: "tel", url: "url", number: "number", date: "date" } as const;

/** The browser input type for a text input: an explicit `attr.type`, else its validation format. */
export function nativeInputType(input: FormInput): string {
  if (input.input_type === "password") return "password";
  const format = input.validation?.format;
  return input.attr?.type || (format ? NATIVE_INPUT_TYPES[format] : "text");
}

export function choiceOptions(input: FormInput): { value: string; label: string }[] {
  if (input.options?.length) return input.options;
  return (input.values ?? []).map((value) => ({ value, label: value }));
}

export function choiceVariant(input: FormInput): "single-checkbox" | "checkboxes" | "radio" {
  const count = choiceOptions(input).length;
  if (input.attr?.variant === "checkbox") return count <= 1 ? "single-checkbox" : "checkboxes";
  if (input.attr?.variant === "radio") return "radio";
  return count <= 1 ? "single-checkbox" : "radio";
}

/** Non-empty answers, in form order. */
export function collectAnswers(form: AgentForm, values: Record<string, string>): FormAnswer[] {
  return form.form_inputs
    .map((input) => ({ fieldId: input.name, label: input.label, value: (values[input.name] ?? "").trim() }))
    .filter((answer) => answer.value);
}

export function formatSubmission(form: AgentForm, answers: FormAnswer[]): string {
  return [
    `<form_submission label="${form.form_name}">`,
    ...answers.map((answer) => `- ${answer.label}: ${answer.value}`),
    "</form_submission>",
    "",
    "Fields:",
    ...answers.map((answer) => `- ${answer.fieldId}="${answer.value.replace(/\n/g, " ")}"`),
  ].join("\n");
}
