import { HttpError } from "../../../services/http/client";

/** What to tell a person when a Leads request fails; the API writes its refusals to be shown. */
export function leadsErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof HttpError && error.status === 403) return "Only the account's admins can do this.";
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
