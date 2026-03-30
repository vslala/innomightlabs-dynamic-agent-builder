import type {
  AnalyticsBreakpoint,
  AnalyticsDashboardState,
  DashboardFiltersChangedDetail,
  DatePreset,
  SourceFilter,
  TimeseriesPoint,
} from "./types";

export function buildDateRangeFromPreset(
  preset: DatePreset,
  timezone: string
): DashboardFiltersChangedDetail {
  const now = new Date();
  const days = preset === "7d" ? 7 : preset === "90d" ? 90 : 30;
  const from = new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  return {
    preset,
    sourceFilter: "all",
    from: from.toISOString(),
    to: now.toISOString(),
    tz: timezone,
  };
}

export function buildFiltersFromConfig(
  preset: DatePreset,
  sourceFilter: SourceFilter,
  timezone: string
): DashboardFiltersChangedDetail {
  const base = buildDateRangeFromPreset(preset, timezone);
  return {
    ...base,
    sourceFilter,
  };
}

export function generateWidgetInstanceId(widgetType: string): string {
  return `${widgetType}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function groupSeriesBySource(series: TimeseriesPoint[]): Record<string, TimeseriesPoint[]> {
  return series.reduce<Record<string, TimeseriesPoint[]>>((acc, point) => {
    const key = point.source ?? "all";
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(point);
    return acc;
  }, {});
}

export function mergeSeriesByBucket(series: TimeseriesPoint[]): TimeseriesPoint[] {
  const map = new Map<string, TimeseriesPoint>();
  for (const point of series) {
    const existing = map.get(point.bucket_start);
    if (existing) {
      existing.value += point.value;
      continue;
    }
    map.set(point.bucket_start, {
      bucket_start: point.bucket_start,
      bucket_label: point.bucket_label,
      value: point.value,
      source: null,
    });
  }
  return Array.from(map.values()).sort((a, b) => a.bucket_start.localeCompare(b.bucket_start));
}

export function getWidgetTitle(defaultTitle: string, override?: string): string {
  return override && override.trim().length > 0 ? override.trim() : defaultTitle;
}

export function cloneDashboardState(state: AnalyticsDashboardState): AnalyticsDashboardState {
  return {
    version: state.version,
    widgets: state.widgets.map((widget) => ({
      instanceId: widget.instanceId,
      widgetType: widget.widgetType,
      config: structuredClone(widget.config),
    })),
    layouts: Object.fromEntries(
      Object.entries(state.layouts).map(([breakpoint, layout]) => [
        breakpoint,
        layout.map((item) => ({ ...item })),
      ])
    ) as AnalyticsDashboardState["layouts"],
  };
}

export function getBottomY(layout: ReadonlyArray<{ y: number; h: number }>): number {
  return layout.reduce((max, item) => Math.max(max, item.y + item.h), 0);
}

export function sortBreakpointKeys(a: AnalyticsBreakpoint, b: AnalyticsBreakpoint): number {
  const order: AnalyticsBreakpoint[] = ["lg", "md", "sm", "xs", "xxs"];
  return order.indexOf(a) - order.indexOf(b);
}

export function formatMetricNumber(value: number): string {
  return value.toLocaleString();
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
