/** On unless set to "false", so leaving it unset keeps today's behaviour. */
const notDisabled = (value: unknown): boolean => value !== "false";

export const featureFlags = {
  /** The "Agent activity" panel listing the tools a turn ran (and its detailed debug view). */
  showToolActivity: notDisabled(import.meta.env.VITE_SHOW_TOOL_ACTIVITY),
} as const;
