import { useEffect, useState } from "react";

export type DelayedPhase = "idle" | "pending" | "slow" | "very-slow";

/** The returned cleanup also cancels callbacks on unmount or a settled request. */
export function scheduleDelayedPhase(
  update: (phase: DelayedPhase) => void,
  schedule = globalThis.setTimeout,
  cancel = globalThis.clearTimeout,
): () => void {
  const slow = schedule(() => update("slow"), 250);
  const verySlow = schedule(() => update("very-slow"), 1500);
  return () => { cancel(slow); cancel(verySlow); };
}

export function scheduleGuestAcceptance(accept: () => void): () => void {
  const timer = setTimeout(accept, 400);
  return () => clearTimeout(timer);
}

export function useDelayedPhase(pending: boolean): DelayedPhase {
  const [phase, setPhase] = useState<DelayedPhase>("pending");
  useEffect(() => {
    if (!pending) return;
    const cancel = scheduleDelayedPhase(setPhase);
    return () => { cancel(); setPhase("pending"); };
  }, [pending]);
  return pending ? phase : "idle";
}
