import { HttpError } from "../http/client";

/** The `code` of an IAM API error (`{detail: {code, message}}`), when there is one. */
export function iamErrorCode(error: unknown): string | undefined {
  if (!(error instanceof HttpError)) return undefined;
  const detail = error.detail;
  return typeof detail === "object" && detail !== null && "code" in detail && typeof detail.code === "string"
    ? detail.code : undefined;
}

// What to do next, for the refusals a person can act on; the API's message says what happened
const NEXT_STEP: Record<string, string> = {
  SEAT_LIMIT_UNAVAILABLE: "Please contact the account administrator to check billing and seat availability, then retry.",
  SEAT_LIMIT_REACHED: "Ask the account administrator to free a seat or upgrade the plan.",
  ESCALATION: "Ask the account owner to grant it, or to give you the permissions it contains.",
  CONFLICT: "The page has been reloaded with the latest permissions.",
};

/** An IAM error as a sentence for the page: the API's message, then what to do about it. */
export function iamErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : "Please try again.";
  const next = NEXT_STEP[iamErrorCode(error) ?? ""];
  return next ? `${message} ${next}` : message;
}
