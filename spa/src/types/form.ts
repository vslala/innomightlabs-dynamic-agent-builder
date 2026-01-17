/**
 * Form schema types matching backend form_models.py
 */

export type FormInputType = "text" | "text_area" | "password" | "select" | "choice";

export interface FormInput {
  input_type: FormInputType;
  name: string;
  label: string;
  value?: string | null;
  values?: string[] | null;
  attr?: Record<string, string> | null;
}

export interface FormSchema {
  form_name: string;
  submit_path: string;
  form_inputs: FormInput[];
}
