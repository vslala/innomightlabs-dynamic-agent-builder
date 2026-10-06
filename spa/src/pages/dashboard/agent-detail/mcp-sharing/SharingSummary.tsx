import { Lock, Users } from "lucide-react";

import { cn } from "../../../../lib/utils";
import type { MCPSharingSummary } from "../../../../types/connectors";
import { sharingLabel } from "./sharingDraft";
import styles from "./MCPSharingDialog.module.css";

export function SharingSummary({ summary }: { summary: MCPSharingSummary }) {
  const shared = summary.available_to.length > 0;
  const Icon = shared ? Users : Lock;
  return (
    <p className={cn(styles.sharingSummary, shared && styles.sharingSummaryShared)}>
      <Icon />
      {sharingLabel(summary)}
      {summary.consent_outdated && <span className={styles.reviewTerms}>· Review updated terms</span>}
    </p>
  );
}
