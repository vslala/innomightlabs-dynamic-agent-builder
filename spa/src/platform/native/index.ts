import { App } from "@capacitor/app";
import { SplashScreen } from "@capacitor/splash-screen";
import type { Platform } from "../types";
import { createNativeAuth } from "./auth";
import { createNativeFiles } from "./files";
import { createNativeLinks } from "./links";
import { createNativeStorage } from "./storage";
import { followThemeWithStatusBar } from "./statusBar";
import { createNativeTokens, type Vault } from "./tokens";
import { openVault } from "./vault";

const SCHEME: string = import.meta.env.VITE_NATIVE_APP_SCHEME || "com.innomightlabs.app";
const DEVICE_ID_KEY = "device_id";

/** The iOS and Android apps (Capacitor). Only this folder imports Capacitor. */
export function createNativePlatform(): Platform {
  let vault: Vault | null = null;
  let deviceId = "";
  const storage = createNativeStorage();
  const tokens = createNativeTokens(
    { get: (key) => vault!.get(key), set: (key, value) => vault!.set(key, value), remove: (key) => vault!.remove(key) },
    () => deviceId,
  );

  return {
    kind: "native",
    tokens,
    storage,
    auth: createNativeAuth(tokens, storage, () => deviceId),
    links: createNativeLinks(SCHEME),
    lifecycle: {
      // Capacitor's resume, not visibilitychange: the web view fires both, and one resync is enough.
      onResume: (handler) => {
        const listener = App.addListener("resume", handler);
        return () => void listener.then((handle) => handle.remove());
      },
    },
    files: createNativeFiles(),
    push: null,
    // App Store 3.1.1 / Play billing: nothing is sold in the app until in-app purchases exist (Phase 4).
    commerce: { canSellSubscriptions: false },
    publicSite: false,
    ready: async () => {
      followThemeWithStatusBar();
      try {
        vault = await openVault();
        deviceId = (await vault.get(DEVICE_ID_KEY)) ?? "";
        if (!deviceId) {
          // A random id for this install, not a hardware id: it keys this device's refresh token.
          deviceId = crypto.randomUUID();
          await vault.set(DEVICE_ID_KEY, deviceId);
        }
        await Promise.all([storage.load(), tokens.load()]);
        if (tokens.needsRefresh()) await tokens.refresh();
      } finally {
        // The first screen is now the right one (dashboard or login): no flash of the other.
        await SplashScreen.hide();
      }
    },
  };
}
