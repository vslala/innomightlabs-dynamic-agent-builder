import type { Platform } from "./types";

export type * from "./types";

let current: Platform | null = null;

/**
 * Called once by main.tsx before the first render. The adapter is chosen by the build, not by asking at runtime,
 * so the website bundle carries no native code. Only the web adapter exists until the app shells (Phase 1);
 * that phase adds the `VITE_PLATFORM === "native"` branch here.
 */
export async function initPlatform(): Promise<Platform> {
  current = (await import("./web")).createWebPlatform();
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
