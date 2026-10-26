import { useMemo, useState } from "react";
import { ShieldCheck } from "lucide-react";

import { Button, StatusBadge, Textarea } from "../../ui";
import type { ConsentBlock, ConsentDecision, ConsentRequest, ConsentState } from "../../../types/consent";
import { ConsentBlockView, type BlockEdit } from "./blocks";
import { shownArguments } from "./shownArguments";
import styles from "./ConsentCard.module.css";

const STATE_LABELS: Record<ConsentState, [string, "pending" | "in_progress" | "success" | "error" | "cancelled" | "warning"]> = {
  pending: ["Waiting for you", "pending"],
  approved: ["Approved", "in_progress"],
  running: ["Running…", "in_progress"],
  succeeded: ["Done", "success"],
  failed: ["Failed", "error"],
  rejected: ["Rejected", "cancelled"],
  superseded: ["Replaced by a newer one", "cancelled"],
  expired: ["Expired", "cancelled"],
  unknown: ["Outcome unknown: check before trying again", "warning"],
};

type Stage = "deciding" | "editing" | "always" | "rejecting" | "sending";

/** The blocks of a card, editable in place when `edit` is set. Shared with the automation editor's step approval. */
export function ConsentBlocks({ blocks, edit }: { blocks: ConsentBlock[]; edit?: BlockEdit }) {
  return (
    <div className={styles.blocks}>
      {blocks.map((block, index) => (
        <ConsentBlockView key={`${block.kind}-${index}`} block={block} edit={edit} />
      ))}
    </div>
  );
}

/**
 * An action the agent wants to take for the person, shown exactly as it will run, for them to approve, edit, always
 * allow or reject. Once decided it stays in the chat with what happened. See docs/LLD-action-consent.md.
 */
export function ConsentCard({
  consent,
  agentName,
  onDecide,
  disabled,
}: {
  consent: ConsentRequest;
  agentName?: string;
  /** Absent where the person can't decide (it isn't their card): the card only shows. */
  onDecide?: (decision: ConsentDecision) => Promise<void>;
  disabled?: boolean;
}) {
  const [stage, setStage] = useState<Stage>("deciding");
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const deciding = consent.state === "pending" && Boolean(onDecide);
  const editableShown = useMemo(() => {
    const shown = shownArguments(consent.blocks);
    return new Set(consent.editable.filter((argument) => shown.has(argument)));
  }, [consent.blocks, consent.editable]);
  // An automation step's ticks are edited straight away; everything else after "Edit"
  const ticksOnly = consent.subject_kind === "automation_steps";
  const editing = deciding && (stage === "editing" || (ticksOnly && stage !== "sending"));
  const edit: BlockEdit | undefined = editing
    ? { editable: editableShown, draft, onChange: (argument, value) => setDraft((current) => ({ ...current, [argument]: value })) }
    : undefined;

  const decide = async (decision: ConsentDecision) => {
    if (!onDecide) return;
    setStage("sending");
    setError(null);
    try {
      await onDecide(decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't go through. Try again.");
      setStage("deciding");
    }
  };
  const approve = (always = false) => decide({ decision: "approve", always, ...(Object.keys(draft).length ? { edits: draft } : {}) });

  const [label, badge] = STATE_LABELS[consent.state];
  const busy = disabled || stage === "sending";

  return (
    <section className={styles.card} aria-label={consent.title}>
      <header className={styles.header}>
        <div className={styles.icon}>
          <ShieldCheck className="h-5 w-5" aria-hidden />
        </div>
        <div className={styles.heading}>
          <div className={styles.title}>{consent.title}</div>
          {consent.summary && <p className={styles.summary}>{consent.summary}</p>}
        </div>
        <StatusBadge status={badge} label={consent.always ? `${label} · always allowed` : label} size="sm" />
      </header>

      <ConsentBlocks blocks={consent.blocks} edit={edit} />

      {consent.state === "rejected" && consent.reason && <p className={styles.muted}>Your reason: {consent.reason}</p>}
      {error && <p className={styles.error}>{error}</p>}

      {deciding && stage === "rejecting" && (
        <div className={styles.confirm}>
          <Textarea
            aria-label="Why not (optional)"
            placeholder="Why not? The agent reads this (optional)."
            rows={2}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className={styles.actions}>
            <Button size="sm" variant="destructive" disabled={busy} onClick={() => decide({ decision: "reject", ...(reason.trim() ? { reason: reason.trim() } : {}) })}>
              Reject
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStage("deciding")}>
              Back
            </Button>
          </div>
        </div>
      )}

      {deciding && stage === "always" && (
        <div className={styles.confirm}>
          <p className={styles.summary}>
            Always allow {agentName ?? "this agent"} to {consent.title.charAt(0).toLowerCase() + consent.title.slice(1)}?
            It won't ask again, in chat or when it runs on a schedule, until you change it on the agent's Skills or MCP
            tools page.
          </p>
          <div className={styles.actions}>
            <Button size="sm" disabled={busy} onClick={() => approve(true)}>
              Approve and always allow
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStage("deciding")}>
              Back
            </Button>
          </div>
        </div>
      )}

      {deciding && (stage === "deciding" || stage === "editing" || stage === "sending") && (
        <div className={styles.actions}>
          <Button size="sm" disabled={busy} onClick={() => approve()}>
            {stage === "editing" && Object.keys(draft).length ? "Approve with changes" : ticksOnly ? "Approve steps" : "Approve"}
          </Button>
          {!ticksOnly && stage !== "editing" && editableShown.size > 0 && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setStage("editing")}>
              Edit
            </Button>
          )}
          {stage === "editing" && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setDraft({}); setStage("deciding"); }}>
              Discard changes
            </Button>
          )}
          {!ticksOnly && stage !== "editing" && (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => setStage("always")}>
              Always allow
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => setStage("rejecting")}>
            Reject
          </Button>
        </div>
      )}
    </section>
  );
}
