import type { LayoutItem, ResponsiveLayouts } from "react-grid-layout";

export type AnalyticsSource = "dashboard" | "widget";
export type SourceFilter = "all" | AnalyticsSource;
export type DatePreset = "7d" | "30d" | "90d";
export type TimeseriesMetric = "messages" | "conversations" | "unique_users";
export type TimeseriesBucket = "day" | "week";
export type WidgetType =
  | "filters"
  | "overview-stats"
  | "message-mix"
  | "messages-over-time"
  | "conversations-over-time"
  | "unique-users-over-time"
  | "top-activity";

export interface AnalyticsWindow {
  from: string;
  to: string;
  tz: string;
  sources: AnalyticsSource[];
}

export interface AnalyticsMeta {
  truncated: boolean;
  truncation_reason?: string | null;
  conversations_scanned: number;
  messages_scanned: number;
}

export interface AnalyticsTotals {
  conversations: number;
  messages: number;
  user_messages: number;
  assistant_messages: number;
  system_messages: number;
  unique_users: number;
  active_days: number;
}

export interface AnalyticsRatios {
  assistant_to_user: number;
  dropoff_rate: number;
  zero_assistant_conversation_rate: number;
}

export interface AnalyticsPercentiles {
  avg: number;
  p50: number;
  p90: number;
}

export interface AnalyticsDistribution {
  messages_per_conversation: AnalyticsPercentiles;
  assistant_messages_per_conversation: AnalyticsPercentiles;
}

export interface TopConversation {
  conversation_id: string;
  title: string;
  source: AnalyticsSource;
  messages: number;
}

export interface TopUser {
  user: string;
  source: AnalyticsSource;
  messages: number;
}

export interface AnalyticsTop {
  longest_conversations: TopConversation[];
  most_active_users: TopUser[];
}

export interface AnalyticsOverviewResponse {
  agent_id: string;
  window: AnalyticsWindow;
  totals: AnalyticsTotals;
  ratios: AnalyticsRatios;
  distribution: AnalyticsDistribution;
  top: AnalyticsTop;
  breakdown_by_source: Partial<Record<AnalyticsSource, AnalyticsTotals>>;
  meta: AnalyticsMeta;
}

export interface TimeseriesPoint {
  bucket_start: string;
  bucket_label: string;
  value: number;
  source?: AnalyticsSource | null;
}

export interface AnalyticsTimeseriesResponse {
  agent_id: string;
  window: AnalyticsWindow;
  metric: TimeseriesMetric;
  bucket: TimeseriesBucket;
  series: TimeseriesPoint[];
  meta: AnalyticsMeta;
}

export interface AnalyticsQueryParams {
  from: string;
  to: string;
  tz: string;
  sources?: AnalyticsSource[];
}

export interface DashboardFiltersState {
  preset: DatePreset;
  sourceFilter: SourceFilter;
}

export interface DashboardFiltersChangedDetail extends DashboardFiltersState {
  from: string;
  to: string;
  tz: string;
}

export interface BaseWidgetConfig {
  title?: string;
}

export interface DashboardFiltersWidgetConfig {
  preset: DatePreset;
  sourceFilter: SourceFilter;
}

export interface OverviewStatsWidgetConfig extends BaseWidgetConfig {}

export interface MessageMixWidgetConfig extends BaseWidgetConfig {}

export interface TimeseriesWidgetConfig extends BaseWidgetConfig {
  bucket: TimeseriesBucket;
  chartVariant: "line" | "bar";
  showSourceSplit: boolean;
}

export interface TopActivityWidgetConfig extends BaseWidgetConfig {
  limit: number;
  mode: "users" | "conversations" | "both";
}

export type AnalyticsWidgetConfig =
  | DashboardFiltersWidgetConfig
  | OverviewStatsWidgetConfig
  | MessageMixWidgetConfig
  | TimeseriesWidgetConfig
  | TopActivityWidgetConfig;

export interface WidgetDefinitionSize {
  w: number;
  h: number;
  minW?: number;
  minH?: number;
}

export interface WidgetInstance<TConfig extends AnalyticsWidgetConfig = AnalyticsWidgetConfig> {
  instanceId: string;
  widgetType: WidgetType;
  config: TConfig;
}

export interface AnalyticsDashboardState {
  version: number;
  widgets: WidgetInstance[];
  layouts: ResponsiveLayouts<AnalyticsBreakpoint>;
}

export interface AnalyticsWidgetBaseProps<TConfig extends AnalyticsWidgetConfig = AnalyticsWidgetConfig> {
  agentId: string;
  instanceId: string;
  config: TConfig;
  onConfigure?: () => void;
  onRemove?: () => void;
  onConfigChange?: (config: TConfig) => void;
}

export interface WidgetDefinition<TConfig extends AnalyticsWidgetConfig = AnalyticsWidgetConfig> {
  widgetType: WidgetType;
  displayName: string;
  description: string;
  defaultSize: WidgetDefinitionSize;
  defaultConfig: TConfig;
  supportsConfig: boolean;
  singleton?: boolean;
  removable?: boolean;
}

export type AnalyticsBreakpoint = "lg" | "md" | "sm" | "xs" | "xxs";

export type AnalyticsLayoutItem = LayoutItem;
