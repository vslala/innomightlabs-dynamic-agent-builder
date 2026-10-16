import styles from "./IlaWorking.module.css";
import { useHeldLabel } from "./useHeldLabel";

/**
 * What Ila is doing right now, as one quiet line: the tool she's running, in plain words, then the next. It is
 * the widget's "Using a tool…" in the style of ChatGPT and Claude, and it goes when her reply starts to stream.
 */
export function IlaWorking({ label }: { label: string }) {
  const shown = useHeldLabel(label);
  return (
    <div className={styles.line} role="status" aria-live="polite">
      <span className={styles.pulse} aria-hidden="true" />
      <span key={shown} className={styles.label}>
        {shown}
      </span>
    </div>
  );
}
