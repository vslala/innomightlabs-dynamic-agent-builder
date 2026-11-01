import type { CapacitorConfig } from "@capacitor/cli";

/** The iOS and Android shells around the SPA's native build (docs/LLD-mobile-ready-app.md, section 4). */
const config: CapacitorConfig = {
  appId: "com.innomightlabs.app",
  appName: "InnoMight",
  webDir: "dist-native",
  ios: { contentInset: "never", scheme: "InnoMight" },
  android: { allowMixedContent: false },
  plugins: {
    // The web view shrinks with the keyboard, so the composer stays above it.
    Keyboard: { resize: "native" },
    // The native adapter's ready() hides it once the session is known: no flash of the login page.
    SplashScreen: { launchAutoHide: false },
  },
};

export default config;
