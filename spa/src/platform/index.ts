import type { Platform } from "./types";

export type * from "./types";

let current: Platform | null = null;

/**
 * Called once by main.tsx before the first render. The adapter is chosen by the build (`VITE_PLATFORM`, set by
 * `.env.native`), not by asking at runtime: Vite folds the comparison, so the website bundle carries no native code.
 */
export async function initPlatform(): Promise<Platform> {
  current = import.meta.env.VITE_PLATFORM === "native"
    ? (await import("./native")).createNativePlatform()
    : (await import("./web")).createWebPlatform();
  await current.ready();
  return current;
}

/** The platform for this run. Throws if used before initPlatform(): a startup-order bug, not a state. */
export function platform(): Platform {
  if (!current) throw new Error("platform() used before initPlatform()");
  return current;
}

/** Tests only: swap in a fake (see testing.ts) or a real adapter. */
export function setPlatformForTests(fake: Platform | null): void {
  current = fake;
}
