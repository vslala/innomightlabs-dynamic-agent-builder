import type { FormInput, FormInputValidationFormat } from "../../types/form";

/**
 * The kinds of field a person picks when building a form, and how each maps onto the platform's `FormInput`.
 * The schema stays the one source of truth: a kind is only a friendlier way to read and write it.
 */
export interface FormInputKind {
  id: string;
  label: string;
  /** Whether the visitor picks from options the author lists. */
  hasOptions: boolean;
  matches: (input: FormInput) => boolean;
  /** `input` reshaped into this kind, keeping its name, label and the hints that still apply. */
  shape: (input: FormInput) => FormInput;
}

const variant = (input: FormInput) => input.attr?.variant;
const format = (input: FormInput) => input.validation?.format ?? null;
const optionCount = (input: FormInput) => (input.options?.length ?? 0) + (input.values?.length ?? 0);

function textKind(id: string, label: string, validationFormat: FormInputValidationFormat | null): FormInputKind {
  return {
    id,
    label,
    hasOptions: false,
    matches: (input) => input.input_type === "text" && format(input) === validationFormat,
    shape: (input) => ({
      ...plain(input),
      input_type: "text",
      validation: validationFormat ? { format: validationFormat } : null,
    }),
  };
}

export const FORM_INPUT_KINDS: FormInputKind[] = [
  textKind("text", "Short text", null),
  {
    id: "long_text",
    label: "Long text",
    hasOptions: false,
    matches: (input) => input.input_type === "text_area",
    shape: (input) => ({ ...plain(input), input_type: "text_area" }),
  },
  textKind("email", "Email", "email"),
  textKind("phone", "Phone", "phone"),
  textKind("url", "Link", "url"),
  textKind("number", "Number", "number"),
  textKind("date", "Date", "date"),
  {
    id: "select",
    label: "Dropdown",
    hasOptions: true,
    matches: (input) => input.input_type === "select",
    shape: (input) => ({ ...withOptions(input), input_type: "select" }),
  },
  {
    id: "radio",
    label: "Pick one",
    hasOptions: true,
    matches: (input) => input.input_type === "choice" && variant(input) !== "checkbox",
    shape: (input) => ({ ...withOptions(input), input_type: "choice", attr: { ...plain(input).attr, variant: "radio" } }),
  },
  {
    id: "checkboxes",
    label: "Pick several",
    hasOptions: true,
    matches: (input) => input.input_type === "choice" && variant(input) === "checkbox" && optionCount(input) > 1,
    shape: (input) => ({ ...withOptions(input), input_type: "choice", attr: { ...plain(input).attr, variant: "checkbox" } }),
  },
  {
    id: "consent",
    label: "Consent checkbox",
    hasOptions: false,
    matches: (input) => input.input_type === "choice" && variant(input) === "checkbox" && optionCount(input) <= 1,
    shape: (input) => ({
      ...plain(input),
      input_type: "choice",
      values: ["yes"],
      attr: { ...plain(input).attr, variant: "checkbox" },
    }),
  },
  {
    id: "file",
    label: "File upload",
    hasOptions: false,
    matches: (input) => input.input_type === "file_upload",
    shape: (input) => ({
      ...plain(input),
      input_type: "file_upload",
      validation: { max_items: input.input_type === "file_upload" ? input.validation?.max_items ?? 1 : 1 },
    }),
  },
];

export function kindOf(input: FormInput): FormInputKind {
  return FORM_INPUT_KINDS.find((kind) => kind.matches(input)) ?? FORM_INPUT_KINDS[0];
}

export function kindById(id: string): FormInputKind {
  return FORM_INPUT_KINDS.find((kind) => kind.id === id) ?? FORM_INPUT_KINDS[0];
}

/** The input's own words and hints, without anything that belongs to one kind (options, formats, variants). */
function plain(input: FormInput): FormInput {
  const attr = { ...(input.attr ?? {}) };
  delete attr.variant;
  return {
    input_type: input.input_type,
    name: input.name,
    label: input.label,
    attr: Object.keys(attr).length ? attr : null,
  };
}

function withOptions(input: FormInput): FormInput {
  const options = input.options?.length
    ? input.options
    : (input.values ?? []).map((value) => ({ value, label: value }));
  return { ...plain(input), options: options.length ? options : [{ value: "Option 1", label: "Option 1" }] };
}

/** A field name from its label: what the agent and the answers call it. */
export function inputNameFrom(label: string): string {
  const name = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/^[0-9_]+/, "");
  return name.slice(0, 40) || "field";
}

export function isOptional(input: FormInput): boolean {
  return input.attr?.optional === "true";
}

export function withOptional(input: FormInput, optional: boolean): FormInput {
  return withAttr(input, "optional", optional ? "true" : undefined);
}

/** `input` with one `attr` set, or removed when `value` is empty. */
export function withAttr(input: FormInput, name: string, value: string | undefined): FormInput {
  const attr = { ...(input.attr ?? {}) };
  if (value) attr[name] = value;
  else delete attr[name];
  return { ...input, attr: Object.keys(attr).length ? attr : null };
}
