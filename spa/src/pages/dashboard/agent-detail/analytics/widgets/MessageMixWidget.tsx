import { useEffect, useState } from "react";

import { analyticsApiService } from "../api";
import { getCurrentAnalyticsFilters, sourceFilterToSources, subscribeAnalyticsFiltersChanged } from "../events";
import type { AnalyticsOverviewResponse, AnalyticsWidgetBaseProps, DashboardFiltersChangedDetail, MessageMixWidgetConfig } from "../types";
import { formatPercent, getWidgetTitle } from "../utils";
import { AnalyticsWidgetFrame } from "./AnalyticsWidgetFrame";
import { FiltersFootnote, WidgetEmptyState, WidgetErrorState, WidgetLoadingState } from "./shared";

export function MessageMixWidget({
  agentId,
  config,
  onConfigure,
  onRemove,
}: AnalyticsWidgetBaseProps<MessageMixWidgetConfig>) {
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
          setError(err instanceof Error ? err.message : "Failed to load message mix");
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
      title={getWidgetTitle("Message Mix", config.title)}
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
        <WidgetEmptyState message="No message mix data available." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {[
            { label: "User messages", value: data.totals.user_messages, color: "#60a5fa" },
            { label: "Assistant messages", value: data.totals.assistant_messages, color: "#34d399" },
            { label: "System messages", value: data.totals.system_messages, color: "#f59e0b" },
          ].map((item) => {
            const total = Math.max(data.totals.messages, 1);
            const ratio = item.value / total;
            return (
              <div key={item.label}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.25rem" }}>
                  <span style={{ fontSize: "0.875rem", color: "var(--text-primary)" }}>{item.label}</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {item.value} • {formatPercent(ratio)}
                  </span>
                </div>
                <div style={{ height: "0.5rem", borderRadius: "999px", background: "var(--bg-secondary)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(ratio * 100, 100)}%`, height: "100%", background: item.color }} />
                </div>
              </div>
            );
          })}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem", marginTop: "0.5rem" }}>
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Assistant / User</p>
              <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>{data.ratios.assistant_to_user.toFixed(2)}</p>
            </div>
            <div>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Dropoff rate</p>
              <p style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)" }}>{formatPercent(data.ratios.dropoff_rate)}</p>
            </div>
          </div>
          <FiltersFootnote filters={filters} />
        </div>
      )}
    </AnalyticsWidgetFrame>
  );
}
