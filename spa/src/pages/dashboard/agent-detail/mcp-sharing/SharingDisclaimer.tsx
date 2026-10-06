import { ShieldAlert } from "lucide-react";

import { Checkbox } from "../../../../components/ui";
import styles from "./MCPSharingDialog.module.css";

interface SharingDisclaimerProps {
  connectionName: string;
  paragraphs: string[];
  accepted: boolean;
  onAcceptedChange: (accepted: boolean) => void;
}

/** The words come from the API, so changing them never needs a dashboard release. */
export function SharingDisclaimer({ connectionName, paragraphs, accepted, onAcceptedChange }: SharingDisclaimerProps) {
  return (
    <div className={styles.disclaimer}>
      <div className={styles.disclaimerHeading}>
        <ShieldAlert className="h-4 w-4" />
        They will be using your {connectionName} account
      </div>
      <ul className={styles.disclaimerPoints}>
        {paragraphs.map((paragraph) => (
          <li key={paragraph}>{paragraph}</li>
        ))}
      </ul>
      <label className={styles.consent}>
        <Checkbox checked={accepted} onChange={(event) => onAcceptedChange(event.target.checked)} />
        I understand these calls use my {connectionName} account.
      </label>
    </div>
  );
}
