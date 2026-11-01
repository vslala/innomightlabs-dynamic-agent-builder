import { StatusBar, Style } from "@capacitor/status-bar";

/**
 * The page draws under the status bar, so its text must contrast with the app's theme, not the phone's:
 * light text on the dark theme (`Style.Dark`), dark text on the light one. Follows theme changes in Settings.
 */
export function followThemeWithStatusBar(): void {
  const apply = () => {
    const light = document.documentElement.dataset.theme === "light";
    void StatusBar.setStyle({ style: light ? Style.Light : Style.Dark }).catch(() => {});
  };
  apply();
  new MutationObserver(apply).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
