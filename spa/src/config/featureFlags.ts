const enabled = (value: unknown): boolean => value === "true";

export const featureFlags = {
  enableDeepResearch: !import.meta.env.PROD && enabled(import.meta.env.VITE_ENABLE_DEEP_RESEARCH),
} as const;
