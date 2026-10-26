/**
 * Consent cards: an action waiting on the person's yes, shown from typed blocks.
 * Mirrors api/src/consent/preview.py and models.py; see docs/LLD-action-consent.md.
 */

export type ConsentBlock =
  | { kind: "text"; label?: string | null; value: string; format: "plain" | "markdown"; argument?: string | null }
  | {
      kind: "email";
      to: string[];
      cc: string[];
      bcc: string[];
      subject: string;
      body: string;
      html_body?: string | null;
      /** The arguments holding the subject and body, so they can be edited in place. */
      arguments: Partial<Record<"subject" | "body", string>>;
    }
  | { kind: "images"; label?: string | null; items: { url: string; alt_text?: string | null }[] }
  | {
      kind: "targets";
      label: string;
      items: { label: string; detail?: string | null; will_run: boolean; reason?: string | null }[];
    }
  | { kind: "fields"; label?: string | null; items: { label: string; value: string; argument?: string | null }[] }
  | {
      kind: "grants";
      label: string;
      /** The edit that carries the ticked keys, `grants:<node_id>`. */
      argument: string;
      items: { key: string; title: string; warning?: string | null; checked: boolean; always_allowed: boolean }[];
    }
  | { kind: "code"; label?: string | null; language: string; value: string }
  | { kind: "warning"; text: string };

export type ConsentBlockKind = ConsentBlock["kind"];

/** The card's state: its status, with `expired` and `unknown` (it died mid-call) derived by the API. */
export type ConsentState =
  | "pending"
  | "approved"
  | "rejected"
  | "superseded"
  | "expired"
  | "running"
  | "succeeded"
  | "failed"
  | "unknown";

export interface ConsentRequest {
  consent_id: string;
  conversation_id: string;
  agent_id: string;
  subject_kind: "skill_action" | "mcp_tool" | "automation_steps";
  key: string;
  title: string;
  summary?: string | null;
  blocks: ConsentBlock[];
  editable: string[];
  state: ConsentState;
  edits: Record<string, unknown>;
  always: boolean;
  reason?: string | null;
  result?: string | null;
  created_at: string;
  decided_at?: string | null;
  expires_at: string;
}

export interface ConsentDecision {
  decision: "approve" | "reject";
  /** Approve, and let this agent do it again without asking until the person changes it back. */
  always?: boolean;
  edits?: Record<string, unknown>;
  reason?: string;
}

/** One action an agent asks about first, and whether its owner always allows it. */
export interface ConsentAction {
  key: string;
  title: string;
  warning?: string | null;
  source: string;
  always_allowed: boolean;
}

/** An automation step that asks its owner first, and where its consent stands. */
export interface StepConsentState {
  node_id: string;
  step: string;
  kind: "action" | "agent";
  required: boolean;
  state: "granted" | "missing" | "stale";
  fingerprint: string;
  title: string;
  blocks: ConsentBlock[];
  granted_actions: string[];
  granted_at?: string | null;
  granted_by?: string | null;
}
