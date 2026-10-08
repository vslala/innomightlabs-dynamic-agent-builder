const enabled = (value: unknown): boolean => value === "true";

/** On unless set to "false", so leaving it unset keeps today's behaviour. */
const notDisabled = (value: unknown): boolean => value !== "false";

export const featureFlags = {
  enableDeepResearch: !import.meta.env.PROD && enabled(import.meta.env.VITE_ENABLE_DEEP_RESEARCH),
  /** The "Agent activity" panel listing the tools a turn ran (and its detailed debug view). */
  showToolActivity: notDisabled(import.meta.env.VITE_SHOW_TOOL_ACTIVITY),
} as const;
