import { useEffect, useState } from "react";
import { holdDelay, MIN_SHOWN_MS } from "./ilaStatus";

/**
 * `latest`, but each line stays up long enough to read: a tool that finishes in a blink doesn't flash past, and the
 * line after it waits its turn. Lines that came and went in between are skipped.
 */
export function useHeldLabel(latest: string, minShown = MIN_SHOWN_MS): string {
  const [held, setHeld] = useState(() => ({ label: latest, since: Date.now() }));

  useEffect(() => {
    if (latest === held.label) return;
    const timer = setTimeout(
      () => setHeld({ label: latest, since: Date.now() }),
      holdDelay(held.since, Date.now(), minShown),
    );
    return () => clearTimeout(timer);
  }, [latest, held, minShown]);

  return held.label;
}
