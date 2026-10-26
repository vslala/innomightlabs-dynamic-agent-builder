import { Check, X } from "lucide-react";

import type { Message } from "../../../types/message";
import { parseConsentDecision } from "./consentDecisionParser";
import styles from "./ConsentDecisionMessage.module.css";

/** "Approved: Publish to social media (edited)": the person's decision on a card, as the chat shows it. */
export function ConsentDecisionMessage({ message }: { message: Message }) {
  const line = parseConsentDecision(message.content);
  if (!line) return null;
  const approved = line.decision === "approved";
  const notes = [line.edited.length ? "edited" : null, line.always ? "always allowed" : null].filter(Boolean);
  return (
    <div className={styles.line}>
      {approved ? <Check className="h-4 w-4" aria-hidden /> : <X className="h-4 w-4" aria-hidden />}
      <span>
        {approved ? "Approved" : "Rejected"}: {line.action}
        {notes.length > 0 && <span className={styles.muted}> ({notes.join(", ")})</span>}
        {line.outcome?.kind === "reason" && <span className={styles.muted}> · {line.outcome.text}</span>}
      </span>
    </div>
  );
}
