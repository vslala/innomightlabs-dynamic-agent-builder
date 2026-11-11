import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "../../lib/utils";
import { Button } from "./button";
import styles from "./copy-button.module.css";

const COPIED_FOR_MS = 1500;

/** An icon button that copies `value`, confirming with a check for a moment. `label` names it for screen readers. */
export function CopyButton({ value, label, className }: { value: string; label: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), COPIED_FOR_MS);
  };

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={cn(styles.copy, className)}
      aria-label={copied ? `${label}: copied` : label}
      title={label}
      onClick={() => void copy()}
    >
      {copied ? <Check className={styles.done} /> : <Copy />}
    </Button>
  );
}
