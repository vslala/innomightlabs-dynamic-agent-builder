import { useEffect, useRef } from "react";
import { platform } from "../platform";

/**
 * Runs `onResume` when the tab or app comes back to the foreground. The latest handler runs, so it may read
 * current state without resubscribing.
 */
export function useAppResume(onResume: () => void): void {
  const latest = useRef(onResume);
  useEffect(() => {
    latest.current = onResume;
  });
  useEffect(() => platform().lifecycle.onResume(() => latest.current()), []);
}
