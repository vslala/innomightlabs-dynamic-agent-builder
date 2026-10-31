/**
 * A checkout a signed-out visitor started on /pricing, finished after they sign in (LoginSuccess). Kept in
 * sessionStorage for this tab only, and only for ten minutes: an old intent must not start a payment later.
 */

const KEY = "pendingCheckout";
const LIFETIME_MS = 10 * 60 * 1000;

export interface PendingCheckout {
  planKey: string;
  billingCycle: string;
  timestamp: number;
}

export function savePendingCheckout(planKey: string, billingCycle: string, now = Date.now()): void {
  const pending: PendingCheckout = { planKey, billingCycle, timestamp: now };
  sessionStorage.setItem(KEY, JSON.stringify(pending));
}

/** The saved checkout if it is still fresh. Removes it either way, so it runs at most once. */
export function takePendingCheckout(now = Date.now()): PendingCheckout | null {
  const saved = sessionStorage.getItem(KEY);
  if (!saved) return null;
  sessionStorage.removeItem(KEY);
  try {
    const pending = JSON.parse(saved) as Partial<PendingCheckout>;
    const fresh = typeof pending.timestamp === "number" && now - pending.timestamp < LIFETIME_MS;
    return fresh && pending.planKey && pending.billingCycle ? (pending as PendingCheckout) : null;
  } catch {
    return null;
  }
}
