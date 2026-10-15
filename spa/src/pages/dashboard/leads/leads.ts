import type { FormInput } from "../../../types/form";
import type { Capture, CaptureFilters } from "../../../types/leads";

/** What an agent's instructions say to use a form: `{{ lead_form:<slug> }}`. */
export function macroFor(slug: string): string {
  return `{{ lead_form:${slug} }}`;
}

/** A slug from a form's name, as the API requires: lower case letters, digits and hyphens. */
export function slugFrom(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 48);
}

/** One answer as text: lists joined, uploads by their file names. */
export function answerText(capture: Capture, input: FormInput): string {
  const answer = capture.answers[input.name];
  if (answer === undefined || answer === "") return "";
  const values = Array.isArray(answer) ? answer : [answer];
  if (input.input_type === "file_upload") {
    return values.map((fileId) => capture.files.find((file) => file.file_id === fileId)?.filename ?? fileId).join(", ");
  }
  return values.join(", ");
}

/** Who the lead is, at a glance: their email if the form asked, else the first answer given. */
export function captureHeadline(capture: Capture): string {
  const email = capture.form_inputs.find((input) => input.validation?.format === "email");
  const first = email && answerText(capture, email)
    ? email
    : capture.form_inputs.find((input) => input.input_type !== "file_upload" && answerText(capture, input));
  return first ? answerText(capture, first) : "No answers";
}

const FILTER_NAMES = ["agent_id", "form", "status", "since", "until"] as const;

/** The list's filters live in the URL, so a filtered view can be shared and survives a reload. */
export function filtersFromSearch(search: URLSearchParams): CaptureFilters {
  const filters: CaptureFilters = {};
  for (const name of FILTER_NAMES) {
    const value = search.get(name);
    if (value) filters[name] = value;
  }
  if (search.get("include_tests") === "true") filters.include_tests = true;
  return filters;
}

export function searchFromFilters(filters: CaptureFilters): URLSearchParams {
  const search = new URLSearchParams();
  for (const name of FILTER_NAMES) {
    const value = filters[name];
    if (value) search.set(name, value);
  }
  if (filters.include_tests) search.set("include_tests", "true");
  return search;
}

export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
