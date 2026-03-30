import { useEffect, useMemo, useState } from "react";

import { analyticsApiService } from "../api";
import { getCurrentAnalyticsFilters, sourceFilterToSources, subscribeAnalyticsFiltersChanged } from "../events";
import type { AnalyticsOverviewResponse, AnalyticsWidgetBaseProps, DashboardFiltersChangedDetail, TopActivityWidgetConfig } from "../types";
import { getWidgetTitle } from "../utils";
import { AnalyticsWidgetFrame } from "./AnalyticsWidgetFrame";
import { FiltersFootnote, WidgetEmptyState, WidgetErrorState, WidgetLoadingState } from "./shared";

export function TopActivityWidget({
  agentId,
  config,
  onConfigure,
  onRemove,
}: AnalyticsWidgetBaseProps<TopActivityWidgetConfig>) {
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
          setError(err instanceof Error ? err.message : "Failed to load top activity");
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

  const topUsers = useMemo(
    () => data?.top.most_active_users.slice(0, config.limit) ?? [],
    [config.limit, data]
  );
  const topConversations = useMemo(
    () => data?.top.longest_conversations.slice(0, config.limit) ?? [],
    [config.limit, data]
  );

  return (
    <AnalyticsWidgetFrame
      title={getWidgetTitle("Top Activity", config.title)}
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
        <WidgetEmptyState message="No top activity available." />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: config.mode === "both" ? "1fr 1fr" : "1fr", gap: "1rem", minHeight: "100%" }}>
          {(config.mode === "users" || config.mode === "both") && (
            <div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-primary)", marginBottom: "0.5rem", fontWeight: 600 }}>Most Active Users</p>
              {topUsers.length === 0 ? (
                <WidgetEmptyState message="No active users in this range." />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {topUsers.map((user, index) => (
                    <div key={`${user.user}-${index}`} style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", fontSize: "0.8125rem" }}>
                      <span style={{ color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.user}</span>
                      <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{user.messages}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {(config.mode === "conversations" || config.mode === "both") && (
            <div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-primary)", marginBottom: "0.5rem", fontWeight: 600 }}>Longest Conversations</p>
              {topConversations.length === 0 ? (
                <WidgetEmptyState message="No conversations in this range." />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {topConversations.map((conversation, index) => (
                    <div key={`${conversation.conversation_id}-${index}`} style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", fontSize: "0.8125rem" }}>
                      <span style={{ color: "var(--text-secondary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{conversation.title}</span>
                      <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{conversation.messages}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div style={{ gridColumn: config.mode === "both" ? "1 / -1" : undefined }}>
            <FiltersFootnote filters={filters} />
          </div>
        </div>
      )}
    </AnalyticsWidgetFrame>
  );
}
