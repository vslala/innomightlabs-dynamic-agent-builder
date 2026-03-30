import type { AnalyticsBreakpoint, WidgetDefinitionSize } from "./types";

export const ANALYTICS_DASHBOARD_VERSION = 1;
export const ANALYTICS_STORAGE_PREFIX = "agent-analytics-dashboard";

export const ANALYTICS_BREAKPOINTS: Record<AnalyticsBreakpoint, number> = {
  lg: 1200,
  md: 996,
  sm: 768,
  xs: 480,
  xxs: 0,
};

export const ANALYTICS_COLS: Record<AnalyticsBreakpoint, number> = {
  lg: 12,
  md: 10,
  sm: 6,
  xs: 4,
  xxs: 2,
};

export const ANALYTICS_ROW_HEIGHT = 34;
export const ANALYTICS_LAYOUT_PADDING: [number, number] = [16, 16];
export const ANALYTICS_MARGIN: [number, number] = [16, 16];

export const DEFAULT_WIDGET_SIZE_BY_BREAKPOINT = (
  size: WidgetDefinitionSize,
  breakpoint: AnalyticsBreakpoint
): WidgetDefinitionSize => {
  const maxCols = ANALYTICS_COLS[breakpoint];
  return {
    ...size,
    w: Math.min(size.w, maxCols),
    minW: size.minW ? Math.min(size.minW, maxCols) : undefined,
  };
};
