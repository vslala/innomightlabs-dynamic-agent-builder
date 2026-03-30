import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { analyticsApiService } from "../api";
import { getCurrentAnalyticsFilters, sourceFilterToSources, subscribeAnalyticsFiltersChanged } from "../events";
import type {
  AnalyticsTimeseriesResponse,
  AnalyticsWidgetBaseProps,
  DashboardFiltersChangedDetail,
  TimeseriesMetric,
  TimeseriesWidgetConfig,
} from "../types";
import { getWidgetTitle, groupSeriesBySource, mergeSeriesByBucket } from "../utils";
import { AnalyticsWidgetFrame } from "./AnalyticsWidgetFrame";
import { FiltersFootnote, WidgetEmptyState, WidgetErrorState, WidgetLoadingState } from "./shared";

const COLORS: Record<string, string> = {
  dashboard: "#60a5fa",
  widget: "#34d399",
  all: "#f59e0b",
};

interface TimeseriesWidgetProps extends AnalyticsWidgetBaseProps<TimeseriesWidgetConfig> {
  metric: TimeseriesMetric;
  defaultTitle: string;
}

export function TimeseriesWidget({
  agentId,
  config,
  metric,
  defaultTitle,
  onConfigure,
  onRemove,
}: TimeseriesWidgetProps) {
  const [filters, setFilters] = useState(getCurrentAnalyticsFilters());
  const [data, setData] = useState<AnalyticsTimeseriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => subscribeAnalyticsFiltersChanged(setFilters), []);

  useEffect(() => {
    let cancelled = false;
    async function loadTimeseries(activeFilters: DashboardFiltersChangedDetail) {
      setLoading(true);
      setError(null);
      try {
        const response = await analyticsApiService.getTimeseries(agentId, {
          metric,
          bucket: config.bucket,
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
          setError(err instanceof Error ? err.message : "Failed to load chart");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void loadTimeseries(filters);
    return () => {
      cancelled = true;
    };
  }, [agentId, metric, config.bucket, filters, refreshNonce, config.showSourceSplit]);

  const chartData = useMemo(() => {
    if (!data) {
      return [];
    }

    if (!config.showSourceSplit) {
      return mergeSeriesByBucket(data.series).map((point) => ({
        bucketLabel: point.bucket_label,
        all: point.value,
      }));
    }

    const grouped = groupSeriesBySource(data.series);
    const byBucket = new Map<string, Record<string, number | string>>();
    Object.entries(grouped).forEach(([source, points]) => {
      points.forEach((point) => {
        const existing = byBucket.get(point.bucket_label) ?? { bucketLabel: point.bucket_label };
        existing[source] = point.value;
        byBucket.set(point.bucket_label, existing);
      });
    });
    return Array.from(byBucket.values());
  }, [config.showSourceSplit, data]);

  const dataKeys = useMemo(() => {
    if (!config.showSourceSplit) {
      return ["all"];
    }
    const unique = new Set<string>();
    data?.series.forEach((point) => {
      unique.add(point.source ?? "all");
    });
    return Array.from(unique);
  }, [config.showSourceSplit, data]);

  const ChartComponent = config.chartVariant === "bar" ? BarChart : LineChart;

  return (
    <AnalyticsWidgetFrame
      title={getWidgetTitle(defaultTitle, config.title)}
      onConfigure={onConfigure}
      onRemove={onRemove}
      onRefresh={() => setRefreshNonce((value) => value + 1)}
      truncated={data?.meta.truncated ?? false}
    >
      {loading ? (
        <WidgetLoadingState />
      ) : error ? (
        <WidgetErrorState message={error} />
      ) : chartData.length === 0 ? (
        <WidgetEmptyState message="No timeseries data available for this range." />
      ) : (
        <div style={{ height: "100%", minHeight: "14rem", display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, minHeight: "12rem" }}>
            <ResponsiveContainer width="100%" height="100%">
              <ChartComponent data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
                <XAxis dataKey="bucketLabel" stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
                <YAxis stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
                <Tooltip />
                <Legend />
                {config.chartVariant === "bar"
                  ? dataKeys.map((key) => (
                      <Bar key={key} dataKey={key} fill={COLORS[key] ?? COLORS.all} radius={[4, 4, 0, 0]} />
                    ))
                  : dataKeys.map((key) => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={key}
                        stroke={COLORS[key] ?? COLORS.all}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
              </ChartComponent>
            </ResponsiveContainer>
          </div>
          <FiltersFootnote filters={filters} />
        </div>
      )}
    </AnalyticsWidgetFrame>
  );
}
