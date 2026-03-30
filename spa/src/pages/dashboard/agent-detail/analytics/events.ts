import type { AnalyticsSource, DashboardFiltersChangedDetail, SourceFilter } from "./types";

export const ANALYTICS_FILTERS_CHANGED = "analytics:filters-changed";
export const ANALYTICS_LAYOUT_RESET = "analytics:layout-reset";

let currentFilters: DashboardFiltersChangedDetail = {
  preset: "30d",
  sourceFilter: "all",
  from: "",
  to: "",
  tz: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
};

export function getCurrentAnalyticsFilters(): DashboardFiltersChangedDetail {
  return currentFilters;
}

export function sourceFilterToSources(sourceFilter: SourceFilter): AnalyticsSource[] | undefined {
  if (sourceFilter === "all") {
    return undefined;
  }
  return [sourceFilter];
}

export function setCurrentAnalyticsFilters(filters: DashboardFiltersChangedDetail): void {
  currentFilters = filters;
}

export function emitAnalyticsFiltersChanged(filters: DashboardFiltersChangedDetail): void {
  currentFilters = filters;
  window.dispatchEvent(
    new CustomEvent<DashboardFiltersChangedDetail>(ANALYTICS_FILTERS_CHANGED, {
      detail: filters,
    })
  );
}

export function subscribeAnalyticsFiltersChanged(
  handler: (filters: DashboardFiltersChangedDetail) => void
): () => void {
  const listener = (event: Event) => {
    const customEvent = event as CustomEvent<DashboardFiltersChangedDetail>;
    if (!customEvent.detail) {
      return;
    }
    handler(customEvent.detail);
  };

  window.addEventListener(ANALYTICS_FILTERS_CHANGED, listener as EventListener);
  return () => {
    window.removeEventListener(ANALYTICS_FILTERS_CHANGED, listener as EventListener);
  };
}

export function emitAnalyticsLayoutReset(): void {
  window.dispatchEvent(new CustomEvent(ANALYTICS_LAYOUT_RESET));
}
