import type { FormInput, FormInputValidationFormat } from "../../types/form";

const NATIVE_INPUT_TYPES: Record<FormInputValidationFormat, string> = {
  email: "email",
  phone: "tel",
  url: "url",
  number: "number",
  date: "date",
};

/** The browser input type for a text input: an explicit `attr.type`, else its validation format. */
export function nativeInputType(input: FormInput): string {
  const format = input.validation?.format;
  return input.attr?.type || (format ? NATIVE_INPUT_TYPES[format] : "text");
}
