import type { Message } from "../../../types/message";

/** The person's decision on a consent card, as the user message the API saves for it (`decision_line`). */
export interface ConsentDecisionLine {
  consentId: string;
  action: string;
  decision: "approved" | "rejected";
  edited: string[];
  always: boolean;
  /** What the action returned ("Result") or why it failed, or the person's reason for rejecting it. */
  outcome: { kind: "result" | "failed" | "reason"; text: string } | null;
}

const LINE = /^<consent_decision ([^>]*)>\n([\s\S]*?)<\/consent_decision>$/;
const ATTRIBUTE = /(\w+)="((?:[^"\\]|\\.)*)"/g;
const OUTCOMES = [
  ["Result:\n", "result"],
  ["It failed:\n", "failed"],
  ["Reason: ", "reason"],
] as const;

export function parseConsentDecision(content: string): ConsentDecisionLine | null {
  const match = content.trim().match(LINE);
  if (!match) return null;
  const attributes = Object.fromEntries(
    [...match[1].matchAll(ATTRIBUTE)].map(([, name, value]) => [name, JSON.parse(`"${value}"`) as string])
  );
  if (!attributes.consent_id || (attributes.decision !== "approved" && attributes.decision !== "rejected")) return null;

  const body = match[2];
  const found = OUTCOMES.find(([prefix]) => body.startsWith(prefix));
  return {
    consentId: attributes.consent_id,
    action: attributes.action ?? "",
    decision: attributes.decision,
    edited: attributes.edited ? attributes.edited.split(",") : [],
    always: attributes.always === "true",
    outcome: found ? { kind: found[1], text: body.slice(found[0].length).trim() } : null,
  };
}

export function isConsentDecisionMessage(message: Message): boolean {
  return message.role === "user" && parseConsentDecision(message.content) !== null;
}
