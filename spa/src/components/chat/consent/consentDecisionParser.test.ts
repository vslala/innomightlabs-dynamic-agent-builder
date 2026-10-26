import { describe, expect, it } from "vitest";

import { parseConsentDecision } from "./consentDecisionParser";

describe("parseConsentDecision", () => {
  it("reads an approval with its edits and result", () => {
    const line = parseConsentDecision(
      '<consent_decision consent_id="consent_1" action="Publish to social media" decision="approved" edited="text" always="true">\n' +
        'Result:\n{"status": "published"}\n</consent_decision>'
    );
    expect(line).toEqual({
      consentId: "consent_1",
      action: "Publish to social media",
      decision: "approved",
      edited: ["text"],
      always: true,
      outcome: { kind: "result", text: '{"status": "published"}' },
    });
  });

  it("reads a rejection and its reason, and escaped quotes in the action", () => {
    const line = parseConsentDecision(
      '<consent_decision consent_id="consent_2" action="Send \\"Hi\\"" decision="rejected">\nReason: Too long\n</consent_decision>'
    );
    expect(line?.action).toBe('Send "Hi"');
    expect(line?.decision).toBe("rejected");
    expect(line?.outcome).toEqual({ kind: "reason", text: "Too long" });
  });

  it("ignores anything else", () => {
    expect(parseConsentDecision("Please post this")).toBeNull();
    expect(parseConsentDecision('<consent_decision decision="approved">\n</consent_decision>')).toBeNull();
  });
});
