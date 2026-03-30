import { useEffect, useMemo, useState } from "react";
import { CalendarRange } from "lucide-react";

import { Button } from "../../../../../components/ui/button";
import { AnalyticsWidgetFrame } from "./AnalyticsWidgetFrame";
import { emitAnalyticsFiltersChanged } from "../events";
import type { AnalyticsWidgetBaseProps, DashboardFiltersChangedDetail, DashboardFiltersWidgetConfig } from "../types";
import { buildFiltersFromConfig } from "../utils";

export function DashboardFiltersWidget({
  config,
  onConfigChange,
}: AnalyticsWidgetBaseProps<DashboardFiltersWidgetConfig>) {
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    []
  );
  const [localConfig, setLocalConfig] = useState(config);

  useEffect(() => {
    setLocalConfig(config);
  }, [config]);

  const broadcastFilters = (nextConfig: DashboardFiltersWidgetConfig) => {
    const filters: DashboardFiltersChangedDetail = buildFiltersFromConfig(
      nextConfig.preset,
      nextConfig.sourceFilter,
      timezone
    );
    emitAnalyticsFiltersChanged(filters);
    onConfigChange?.(nextConfig);
  };

  useEffect(() => {
    broadcastFilters(config);
    // Broadcast the persisted state once on mount so other widgets can fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateConfig = (nextConfig: DashboardFiltersWidgetConfig) => {
    setLocalConfig(nextConfig);
    broadcastFilters(nextConfig);
  };

  return (
    <AnalyticsWidgetFrame title="Dashboard Filters" removable={false}>
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", height: "100%" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--text-muted)" }}>
          <CalendarRange className="h-4 w-4" />
          <p style={{ fontSize: "0.875rem" }}>
            Broadcasting date range and source filter to all mounted analytics widgets.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.75rem" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Date Range</label>
            <select
              value={localConfig.preset}
              onChange={(event) =>
                updateConfig({
                  ...localConfig,
                  preset: event.target.value as DashboardFiltersWidgetConfig["preset"],
                })
              }
              style={{
                height: "2.5rem",
                borderRadius: "0.5rem",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-secondary)",
                padding: "0 0.75rem",
              }}
            >
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
            </select>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Source</label>
            <select
              value={localConfig.sourceFilter}
              onChange={(event) =>
                updateConfig({
                  ...localConfig,
                  sourceFilter: event.target.value as DashboardFiltersWidgetConfig["sourceFilter"],
                })
              }
              style={{
                height: "2.5rem",
                borderRadius: "0.5rem",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-secondary)",
                padding: "0 0.75rem",
              }}
            >
              <option value="all">All sources</option>
              <option value="dashboard">Dashboard</option>
              <option value="widget">Widget</option>
            </select>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginTop: "auto" }}>
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Timezone: {timezone}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => updateConfig({ preset: "30d", sourceFilter: "all" })}
          >
            Reset Filters
          </Button>
        </div>
      </div>
    </AnalyticsWidgetFrame>
  );
}
