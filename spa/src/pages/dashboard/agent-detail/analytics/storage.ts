import type { LayoutItem, ResponsiveLayouts } from "react-grid-layout";

import {
  ANALYTICS_COLS,
  ANALYTICS_DASHBOARD_VERSION,
  ANALYTICS_STORAGE_PREFIX,
  DEFAULT_WIDGET_SIZE_BY_BREAKPOINT,
} from "./constants";
import type {
  AnalyticsBreakpoint,
  AnalyticsDashboardState,
  WidgetDefinition,
  WidgetInstance,
  WidgetType,
} from "./types";
import { generateWidgetInstanceId, getBottomY } from "./utils";

const BREAKPOINTS: AnalyticsBreakpoint[] = ["lg", "md", "sm", "xs", "xxs"];

export function getAnalyticsStorageKey(agentId: string): string {
  return `${ANALYTICS_STORAGE_PREFIX}:${agentId}:v${ANALYTICS_DASHBOARD_VERSION}`;
}

export function loadAnalyticsDashboardState(agentId: string): AnalyticsDashboardState | null {
  const raw = localStorage.getItem(getAnalyticsStorageKey(agentId));
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as AnalyticsDashboardState;
    if (parsed.version !== ANALYTICS_DASHBOARD_VERSION) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveAnalyticsDashboardState(agentId: string, state: AnalyticsDashboardState): void {
  localStorage.setItem(getAnalyticsStorageKey(agentId), JSON.stringify(state));
}

export function createDefaultAnalyticsDashboardState(
  registry: Record<WidgetType, WidgetDefinition>
): AnalyticsDashboardState {
  const defaultWidgets: WidgetInstance[] = [
    {
      instanceId: generateWidgetInstanceId("filters"),
      widgetType: "filters",
      config: registry.filters.defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("overview-stats"),
      widgetType: "overview-stats",
      config: registry["overview-stats"].defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("message-mix"),
      widgetType: "message-mix",
      config: registry["message-mix"].defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("messages-over-time"),
      widgetType: "messages-over-time",
      config: registry["messages-over-time"].defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("conversations-over-time"),
      widgetType: "conversations-over-time",
      config: registry["conversations-over-time"].defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("unique-users-over-time"),
      widgetType: "unique-users-over-time",
      config: registry["unique-users-over-time"].defaultConfig,
    },
    {
      instanceId: generateWidgetInstanceId("top-activity"),
      widgetType: "top-activity",
      config: registry["top-activity"].defaultConfig,
    },
  ];

  const layouts = {} as ResponsiveLayouts<AnalyticsBreakpoint>;
  for (const breakpoint of BREAKPOINTS) {
    const cols = ANALYTICS_COLS[breakpoint];
    const entries: LayoutItem[] = [];

    defaultWidgets.forEach((widget, index) => {
      const size = DEFAULT_WIDGET_SIZE_BY_BREAKPOINT(
        registry[widget.widgetType].defaultSize,
        breakpoint
      );
      const y = breakpoint === "lg"
        ? index === 0
          ? 0
          : index <= 2
            ? 4
            : index <= 4
              ? 10
              : 16
        : getBottomY(entries);
      const x = breakpoint === "lg"
        ? index === 1
          ? 0
          : index === 2
            ? 4
            : index === 3
              ? 0
              : index === 4
                ? 6
                : 0
        : 0;

      entries.push({
        i: widget.instanceId,
        x: Math.min(x, Math.max(0, cols - size.w)),
        y,
        w: size.w,
        h: size.h,
        minW: size.minW,
        minH: size.minH,
      });
    });

    layouts[breakpoint] = entries;
  }
  return {
    version: ANALYTICS_DASHBOARD_VERSION,
    widgets: defaultWidgets,
    layouts,
  };
}

export function addWidgetInstanceToState(
  state: AnalyticsDashboardState,
  widget: WidgetInstance,
  definition: WidgetDefinition
): AnalyticsDashboardState {
  const nextState: AnalyticsDashboardState = {
    version: state.version,
    widgets: [...state.widgets, widget],
    layouts: {} as ResponsiveLayouts<AnalyticsBreakpoint>,
  };

  for (const breakpoint of BREAKPOINTS) {
    const existing = (state.layouts[breakpoint] ?? []).map((item: LayoutItem) => ({ ...item }));
    const size = DEFAULT_WIDGET_SIZE_BY_BREAKPOINT(definition.defaultSize, breakpoint);
    existing.push({
      i: widget.instanceId,
      x: 0,
      y: getBottomY(existing),
      w: size.w,
      h: size.h,
      minW: size.minW,
      minH: size.minH,
    });
    nextState.layouts[breakpoint] = existing;
  }

  return nextState;
}

export function removeWidgetInstanceFromState(
  state: AnalyticsDashboardState,
  instanceId: string
): AnalyticsDashboardState {
  return {
    version: state.version,
    widgets: state.widgets.filter((widget) => widget.instanceId !== instanceId),
    layouts: Object.fromEntries(
      BREAKPOINTS.map((breakpoint) => [
        breakpoint,
        (state.layouts[breakpoint] ?? []).filter((item: LayoutItem) => item.i !== instanceId),
      ])
    ) as ResponsiveLayouts<AnalyticsBreakpoint>,
  };
}
