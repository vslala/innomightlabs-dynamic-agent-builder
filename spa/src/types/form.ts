/**
 * Form schema types matching backend form_models.py
 */

export type FormInputType =
  | "text"
  | "text_area"
  | "password"
  | "select"
  | "choice"
  | "file_upload"
  | "key_value";

export type KeyValueFormValue = Record<string, string>;

export type FormValue = string | FileList | File[] | KeyValueFormValue | null;

export interface SelectOption {
  value: string;
  label: string;
}

export interface FormOptionsSource {
  type: string;
  mode?: "hydrate" | "lazy";
  endpoint?: string | null;
}

export type FormInputValidationFormat = "email";

export interface FormInputValidation {
  format?: FormInputValidationFormat | null;
  multiple?: boolean;
  separator?: string;
  min_items?: number | null;
  max_items?: number | null;
}

export interface FormInput {
  input_type: FormInputType;
  name: string;
  label: string;
  value?: string | null;
  values?: string[] | null;
  options?: SelectOption[] | null;  // For value/label pairs
  options_source?: FormOptionsSource | null;
  validation?: FormInputValidation | null;
  attr?: Record<string, string> | null;
}

export interface FormSchema {
  form_name: string;
  submit_path: string;
  form_inputs: FormInput[];
}
