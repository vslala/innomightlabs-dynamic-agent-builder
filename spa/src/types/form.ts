/**
 * Form schema types matching backend form_models.py
 */

export type FormInputType = "text" | "text_area" | "password" | "select" | "choice";

export interface SelectOption {
  value: string;
  label: string;
}

export interface FormInput {
  input_type: FormInputType;
  name: string;
  label: string;
  value?: string | null;
  values?: string[] | null;
  options?: SelectOption[] | null;  // For value/label pairs
  attr?: Record<string, string> | null;
}

export interface FormSchema {
  form_name: string;
  submit_path: string;
  form_inputs: FormInput[];
}
