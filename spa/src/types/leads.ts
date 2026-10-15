/**
 * Leads types, matching api/src/leads/models.py. A lead form's inputs are the platform form schema.
 */

import type { FormInput } from "./form";

export interface LeadFormFields {
  name: string;
  /** Why the account collects this; the agent reads it to explain itself. */
  purpose?: string | null;
  form_inputs: FormInput[];
}

export interface CreateLeadFormRequest extends LeadFormFields {
  slug: string;
}

export interface LeadForm extends LeadFormFields {
  form_id: string;
  account_id: string;
  /** Agents name the form by it, in `{{ lead_form:<slug> }}`; it never changes. */
  slug: string;
  version: number;
  status: "active" | "archived";
  capture_count: number;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

export type LeadStage = "open" | "won" | "lost";

export interface LeadStatus {
  key: string;
  label: string;
  stage: LeadStage;
}

export interface LeadSettings {
  account_id: string;
  /** In order; the first is what new leads get. */
  statuses: LeadStatus[];
}

export interface LeadSettingsRequest {
  statuses: LeadStatus[];
  /** For each removed status that leads still have, the status to move them to. */
  replacements: Record<string, string>;
}

export type CaptureSource = "widget" | "dashboard" | "api" | "a2a";

export interface CaptureFile {
  file_id: string;
  input_name: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export type CaptureAnswer = string | string[];

export interface Capture {
  capture_id: string;
  account_id: string;
  form_id?: string | null;
  form_slug?: string | null;
  form_name: string;
  form_version?: number | null;
  /** The inputs as they were when the lead came in. */
  form_inputs: FormInput[];
  answers: Record<string, CaptureAnswer>;
  files: CaptureFile[];
  agent_id: string;
  conversation_id?: string | null;
  actor_kind: string;
  actor_id: string;
  actor_email?: string | null;
  source: CaptureSource;
  status: string;
  created_at: string;
  updated_at?: string | null;
}

export interface CaptureFilters {
  agent_id?: string;
  form?: string;
  status?: string;
  include_tests?: boolean;
  since?: string;
  until?: string;
}

export interface CapturePage {
  items: Capture[];
  next_cursor?: string | null;
  /** Leads hidden by the plan's monthly limit until the account upgrades. */
  locked_count: number;
}

export interface LeadUsage {
  month: string;
  forms: number;
  forms_limit: number;
  captures: number;
  captures_limit: number;
}

export interface UploadedLeadFile {
  file_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}
