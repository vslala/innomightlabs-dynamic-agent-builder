import { Bot, Check, Globe, KeyRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "../../../../lib/utils";
import type { MCPAudience } from "../../../../types/connectors";
import { SHAREABLE_AUDIENCES } from "../audiences";
import styles from "./MCPSharingDialog.module.css";

const ICONS: Record<MCPAudience, LucideIcon> = { visitor: Globe, api: KeyRound, a2a: Bot };

interface AudiencePickerProps {
  selected: MCPAudience[];
  onToggle: (audience: MCPAudience) => void;
}

export function AudiencePicker({ selected, onToggle }: AudiencePickerProps) {
  return (
    <div className={styles.audiences}>
      {SHAREABLE_AUDIENCES.map(({ kind, label, reach }) => {
        const Icon = ICONS[kind];
        const checked = selected.includes(kind);
        return (
          <button
            key={kind}
            type="button"
            role="checkbox"
            aria-checked={checked}
            className={cn(styles.audience, checked && styles.audienceSelected)}
            onClick={() => onToggle(kind)}
          >
            <span className={styles.audienceIcon}>
              <Icon className="h-4 w-4" />
            </span>
            <span className={styles.audienceText}>
              <span className={styles.audienceLabel}>{label}</span>
              <span className={styles.audienceReach}>{reach}</span>
            </span>
            <span className={styles.audienceCheck}>{checked && <Check className="h-3 w-3" />}</span>
          </button>
        );
      })}
    </div>
  );
}
