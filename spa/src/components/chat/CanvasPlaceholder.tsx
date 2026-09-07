import { AlertTriangle, Loader2 } from "lucide-react";
import styles from "./CanvasPlaceholder.module.css";

interface CanvasPlaceholderProps {
  mode: "loading" | "failed";
}

export function CanvasPlaceholder({ mode }: CanvasPlaceholderProps) {
  if (mode === "failed") {
    return (
      <div className={styles.placeholder}>
        <AlertTriangle className={styles.failedIcon} />
        <span className={styles.message}>This canvas couldn't be loaded.</span>
      </div>
    );
  }

  return (
    <div className={styles.placeholder}>
      <Loader2 className={styles.spinner} />
      <span className={styles.message}>Loading canvas...</span>
    </div>
  );
}
