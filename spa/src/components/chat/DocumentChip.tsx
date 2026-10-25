import { AlertCircle, CheckCircle, FileText, Loader2, X } from "lucide-react";
import { Button } from "../ui/button";
import styles from "./DocumentChip.module.css";

interface DocumentChipProps {
  filename: string;
  /** "Uploading", "Reading", "Ready", "Failed"… shown beside the name, so state never rests on colour alone. */
  label: string;
  state: "busy" | "ready" | "failed";
  /** Why it failed, shown on hover. */
  error?: string;
  onRemove?: () => void;
}

/** A document the conversation has (or is uploading), with how far reading it has got. */
export function DocumentChip({ filename, label, state, error, onRemove }: DocumentChipProps) {
  const Icon = state === "busy" ? Loader2 : state === "failed" ? AlertCircle : CheckCircle;
  return (
    <div className={styles.chip} data-state={state} title={error || filename}>
      <FileText className={styles.icon} aria-hidden="true" />
      <span className={styles.name}>{filename}</span>
      <span className={styles.status} role={state === "busy" ? "status" : undefined}>
        <Icon className={styles.statusIcon} aria-hidden="true" />
        {label}
      </span>
      {onRemove && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={styles.remove}
          onClick={onRemove}
          aria-label={`Remove ${filename}`}
        >
          <X size={12} />
        </Button>
      )}
    </div>
  );
}
