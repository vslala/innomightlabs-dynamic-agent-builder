import { useEffect, useState } from "react";
import { Activity, MessageSquare, Users } from "lucide-react";

import { StatCard } from "../../../../../components/ui/stats";
import { analyticsApiService } from "../api";
import { getCurrentAnalyticsFilters, sourceFilterToSources, subscribeAnalyticsFiltersChanged } from "../events";
import type { AnalyticsOverviewResponse, AnalyticsWidgetBaseProps, DashboardFiltersChangedDetail, OverviewStatsWidgetConfig } from "../types";
import { getWidgetTitle } from "../utils";
import { AnalyticsWidgetFrame } from "./AnalyticsWidgetFrame";
import { WidgetEmptyState, WidgetErrorState, WidgetLoadingState } from "./shared";

export function OverviewStatsWidget({
  agentId,
  config,
  onConfigure,
  onRemove,
}: AnalyticsWidgetBaseProps<OverviewStatsWidgetConfig>) {
  const [filters, setFilters] = useState(getCurrentAnalyticsFilters());
  const [data, setData] = useState<AnalyticsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => subscribeAnalyticsFiltersChanged(setFilters), []);

  useEffect(() => {
    let cancelled = false;
    async function loadOverview(activeFilters: DashboardFiltersChangedDetail) {
      setLoading(true);
      setError(null);
      try {
        const response = await analyticsApiService.getOverview(agentId, {
          from: activeFilters.from,
          to: activeFilters.to,
          tz: activeFilters.tz,
          sources: sourceFilterToSources(activeFilters.sourceFilter),
        });
        if (!cancelled) {
          setData(response);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load overview");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadOverview(filters);
    return () => {
      cancelled = true;
    };
  }, [agentId, filters, refreshNonce]);

  return (
    <AnalyticsWidgetFrame
      title={getWidgetTitle("Overview Stats", config.title)}
      onConfigure={onConfigure}
      onRemove={onRemove}
      onRefresh={() => setRefreshNonce((value) => value + 1)}
      truncated={data?.meta.truncated ?? false}
    >
      {loading ? (
        <WidgetLoadingState />
      ) : error ? (
        <WidgetErrorState message={error} />
      ) : !data ? (
        <WidgetEmptyState message="No analytics data available." />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem" }}>
          <StatCard label="Conversations" value={data.totals.conversations} icon={<MessageSquare className="h-4 w-4" />} />
          <StatCard label="Messages" value={data.totals.messages} icon={<Activity className="h-4 w-4" />} />
          <StatCard label="Unique Users" value={data.totals.unique_users} icon={<Users className="h-4 w-4" />} />
          <StatCard label="Active Days" value={data.totals.active_days} icon={<Activity className="h-4 w-4" />} />
        </div>
      )}
    </AnalyticsWidgetFrame>
  );
}
