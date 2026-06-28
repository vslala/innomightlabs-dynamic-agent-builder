export const THEME_STORAGE_KEY = "innomightlabs.theme";

export type AppTheme = "dark" | "light";

const DEFAULT_THEME: AppTheme = "dark";

export function isAppTheme(value: string | null): value is AppTheme {
  return value === "dark" || value === "light";
}

export function getStoredTheme(): AppTheme {
  if (typeof window === "undefined") {
    return DEFAULT_THEME;
  }
  const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
  return isAppTheme(storedTheme) ? storedTheme : DEFAULT_THEME;
}

export function applyTheme(theme: AppTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function setStoredTheme(theme: AppTheme): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }
  applyTheme(theme);
}
