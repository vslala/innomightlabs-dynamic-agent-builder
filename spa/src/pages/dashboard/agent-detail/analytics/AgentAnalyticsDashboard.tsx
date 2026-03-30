import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { BarChart3, Plus, RotateCcw } from "lucide-react";
import { Responsive, useContainerWidth, type Layout, type ResponsiveLayouts } from "react-grid-layout";

import { Button } from "../../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../../components/ui/dialog";
import { Input } from "../../../../components/ui/input";
import { Label } from "../../../../components/ui/label";
import { analyticsWidgetRegistry } from "./registry";
import {
  createDefaultAnalyticsDashboardState,
  loadAnalyticsDashboardState,
  removeWidgetInstanceFromState,
  saveAnalyticsDashboardState,
  addWidgetInstanceToState,
} from "./storage";
import type {
  AnalyticsDashboardState,
  AnalyticsWidgetConfig,
  AnalyticsWidgetBaseProps,
  DashboardFiltersWidgetConfig,
  MessageMixWidgetConfig,
  OverviewStatsWidgetConfig,
  TimeseriesWidgetConfig,
  TopActivityWidgetConfig,
  WidgetInstance,
  WidgetType,
} from "./types";
import { useAgentDetailContext } from "../types";
import { emitAnalyticsFiltersChanged, emitAnalyticsLayoutReset, setCurrentAnalyticsFilters } from "./events";
import { buildFiltersFromConfig, generateWidgetInstanceId } from "./utils";
import {
  ANALYTICS_BREAKPOINTS,
  ANALYTICS_COLS,
  ANALYTICS_LAYOUT_PADDING,
  ANALYTICS_MARGIN,
  ANALYTICS_ROW_HEIGHT,
} from "./constants";
import { DashboardFiltersWidget } from "./widgets/DashboardFiltersWidget";
import { OverviewStatsWidget } from "./widgets/OverviewStatsWidget";
import { MessageMixWidget } from "./widgets/MessageMixWidget";
import { TimeseriesWidget } from "./widgets/TimeseriesWidget";
import { TopActivityWidget } from "./widgets/TopActivityWidget";

function renderWidget(
  widget: WidgetInstance,
  agentId: string,
  handlers: {
    onConfigure: () => void;
    onRemove?: () => void;
    onConfigChange: (config: AnalyticsWidgetConfig) => void;
  }
) {
  const commonProps: AnalyticsWidgetBaseProps = {
    agentId,
    instanceId: widget.instanceId,
    config: widget.config,
    onConfigure: handlers.onConfigure,
    onRemove: handlers.onRemove,
    onConfigChange: handlers.onConfigChange,
  };

  switch (widget.widgetType) {
    case "filters":
      return <DashboardFiltersWidget {...(commonProps as AnalyticsWidgetBaseProps<DashboardFiltersWidgetConfig>)} />;
    case "overview-stats":
      return <OverviewStatsWidget {...(commonProps as AnalyticsWidgetBaseProps<OverviewStatsWidgetConfig>)} />;
    case "message-mix":
      return <MessageMixWidget {...(commonProps as AnalyticsWidgetBaseProps<MessageMixWidgetConfig>)} />;
    case "messages-over-time":
      return (
        <TimeseriesWidget
          {...(commonProps as AnalyticsWidgetBaseProps<TimeseriesWidgetConfig>)}
          metric="messages"
          defaultTitle="Messages Over Time"
        />
      );
    case "conversations-over-time":
      return (
        <TimeseriesWidget
          {...(commonProps as AnalyticsWidgetBaseProps<TimeseriesWidgetConfig>)}
          metric="conversations"
          defaultTitle="Conversations Over Time"
        />
      );
    case "unique-users-over-time":
      return (
        <TimeseriesWidget
          {...(commonProps as AnalyticsWidgetBaseProps<TimeseriesWidgetConfig>)}
          metric="unique_users"
          defaultTitle="Unique Users Over Time"
        />
      );
    case "top-activity":
      return <TopActivityWidget {...(commonProps as AnalyticsWidgetBaseProps<TopActivityWidgetConfig>)} />;
    default:
      return null;
  }
}

export function AgentAnalyticsDashboard() {
  const { agent } = useAgentDetailContext();
  const { width, containerRef, mounted } = useContainerWidth({ initialWidth: 1280 });
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    []
  );
  const [dashboardState, setDashboardState] = useState<AnalyticsDashboardState>(() => {
    return (
      loadAnalyticsDashboardState(agent.agent_id) ??
      createDefaultAnalyticsDashboardState(analyticsWidgetRegistry)
    );
  });
  const [configuringWidgetId, setConfiguringWidgetId] = useState<string | null>(null);

  useEffect(() => {
    const loaded =
      loadAnalyticsDashboardState(agent.agent_id) ??
      createDefaultAnalyticsDashboardState(analyticsWidgetRegistry);
    setDashboardState(loaded);
  }, [agent.agent_id, timezone]);

  useEffect(() => {
    saveAnalyticsDashboardState(agent.agent_id, dashboardState);
  }, [agent.agent_id, dashboardState]);

  useEffect(() => {
    const filtersWidget = dashboardState.widgets.find((widget) => widget.widgetType === "filters");
    const filterConfig = (filtersWidget?.config ?? analyticsWidgetRegistry.filters.defaultConfig) as DashboardFiltersWidgetConfig;
    const filters = buildFiltersFromConfig(filterConfig.preset, filterConfig.sourceFilter, timezone);
    setCurrentAnalyticsFilters(filters);
    emitAnalyticsFiltersChanged(filters);
  }, [dashboardState.widgets, timezone]);

  const placedWidgetTypes = useMemo(
    () => new Set(dashboardState.widgets.map((widget) => widget.widgetType)),
    [dashboardState.widgets]
  );

  const configuringWidget = dashboardState.widgets.find((widget) => widget.instanceId === configuringWidgetId) ?? null;

  const updateWidgetConfig = (instanceId: string, config: AnalyticsWidgetConfig) => {
    setDashboardState((prev) => ({
      ...prev,
      widgets: prev.widgets.map((widget) =>
        widget.instanceId === instanceId ? { ...widget, config } : widget
      ),
    }));
  };

  const handleAddWidget = (widgetType: WidgetType) => {
    const definition = analyticsWidgetRegistry[widgetType];
    if (definition.singleton && placedWidgetTypes.has(widgetType)) {
      return;
    }
    const widget: WidgetInstance = {
      instanceId: generateWidgetInstanceId(widgetType),
      widgetType,
      config: structuredClone(definition.defaultConfig),
    };
    setDashboardState((prev) => addWidgetInstanceToState(prev, widget, definition));
  };

  const handleRemoveWidget = (instanceId: string) => {
    setDashboardState((prev) => removeWidgetInstanceFromState(prev, instanceId));
    if (configuringWidgetId === instanceId) {
      setConfiguringWidgetId(null);
    }
  };

  const handleLayoutsChange = (_currentLayout: Layout, allLayouts: ResponsiveLayouts<string>) => {
    setDashboardState((prev) => ({
      ...prev,
      layouts: allLayouts as AnalyticsDashboardState["layouts"],
    }));
  };

  const handleResetDashboard = () => {
    const nextState = createDefaultAnalyticsDashboardState(analyticsWidgetRegistry);
    setDashboardState(nextState);
    emitAnalyticsLayoutReset();
  };

  const canRemove = (widget: WidgetInstance) => analyticsWidgetRegistry[widget.widgetType].removable !== false;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <Card>
        <CardHeader>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
            <div>
              <CardTitle className="text-lg">Analytics Dashboard</CardTitle>
              <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginTop: "0.375rem" }}>
                Add widgets, drag them on the canvas, and configure each widget independently.
              </p>
            </div>
            <Button variant="outline" onClick={handleResetDashboard}>
              <RotateCcw className="h-4 w-4 mr-2" />
              Reset Dashboard
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(15rem, 1fr))", gap: "0.75rem" }}>
            {Object.values(analyticsWidgetRegistry).map((definition) => {
              const alreadyPlaced = placedWidgetTypes.has(definition.widgetType);
              const disabled = definition.singleton && alreadyPlaced;

              return (
                <div key={definition.widgetType} style={{ border: "1px solid var(--border-subtle)", borderRadius: "0.75rem", padding: "0.875rem", background: "var(--bg-secondary)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "0.5rem" }}>
                    <p style={{ color: "var(--text-primary)", fontWeight: 600 }}>{definition.displayName}</p>
                    <Button size="sm" onClick={() => handleAddWidget(definition.widgetType)} disabled={disabled}>
                      <Plus className="h-4 w-4 mr-1" />
                      Add
                    </Button>
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>{definition.description}</p>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {dashboardState.widgets.length === 0 ? (
        <Card>
          <CardContent style={{ padding: "3rem 1rem", textAlign: "center", color: "var(--text-muted)" }}>
            <BarChart3 style={{ height: "3rem", width: "3rem", margin: "0 auto 1rem", opacity: 0.5 }} />
            <p>No widgets on the canvas.</p>
            <p style={{ fontSize: "0.875rem" }}>Add a widget from the palette above to start building this agent dashboard.</p>
          </CardContent>
        </Card>
      ) : (
        <div ref={containerRef} style={{ minHeight: "20rem" }}>
          {mounted && (
            <Responsive
              width={width}
              breakpoints={ANALYTICS_BREAKPOINTS}
              cols={ANALYTICS_COLS}
              layouts={dashboardState.layouts}
              rowHeight={ANALYTICS_ROW_HEIGHT}
              margin={ANALYTICS_MARGIN}
              containerPadding={ANALYTICS_LAYOUT_PADDING}
              dragConfig={{ enabled: true, handle: ".analytics-widget-drag-handle" }}
              resizeConfig={{ enabled: true }}
              onLayoutChange={handleLayoutsChange}
              onBreakpointChange={() => undefined}
            >
              {dashboardState.widgets.map((widget) => (
                <div key={widget.instanceId} style={{ overflow: "hidden" }}>
                  {renderWidget(widget, agent.agent_id, {
                    onConfigure: analyticsWidgetRegistry[widget.widgetType].supportsConfig
                      ? () => setConfiguringWidgetId(widget.instanceId)
                      : () => undefined,
                    onRemove: canRemove(widget) ? () => handleRemoveWidget(widget.instanceId) : undefined,
                    onConfigChange: (config) => updateWidgetConfig(widget.instanceId, config),
                  })}
                </div>
              ))}
            </Responsive>
          )}
        </div>
      )}

      <Dialog open={!!configuringWidget} onOpenChange={() => setConfiguringWidgetId(null)}>
        <DialogContent style={{ maxWidth: "32rem" }}>
          <DialogHeader>
            <DialogTitle>Configure Widget</DialogTitle>
            <DialogDescription>
              Update the settings for this widget instance. Changes are persisted per agent.
            </DialogDescription>
          </DialogHeader>
          {configuringWidget && (
            <WidgetConfigEditor
              widget={configuringWidget}
              onSave={(config) => {
                updateWidgetConfig(configuringWidget.instanceId, config);
                setConfiguringWidgetId(null);
              }}
              onCancel={() => setConfiguringWidgetId(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WidgetConfigEditor({
  widget,
  onSave,
  onCancel,
}: {
  widget: WidgetInstance;
  onSave: (config: AnalyticsWidgetConfig) => void;
  onCancel: () => void;
}) {
  const [config, setConfig] = useState<AnalyticsWidgetConfig>(structuredClone(widget.config));

  useEffect(() => {
    setConfig(structuredClone(widget.config));
  }, [widget]);

  return (
    <>
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {"title" in config && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            <Label htmlFor="widget-title">Title override</Label>
            <Input
              id="widget-title"
              value={config.title ?? ""}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setConfig((prev) => ({ ...prev, title: event.target.value }))
              }
            />
          </div>
        )}

        {"bucket" in config && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              <Label htmlFor="widget-bucket">Bucket</Label>
              <select
                id="widget-bucket"
                value={config.bucket}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setConfig((prev) => ({
                    ...(prev as TimeseriesWidgetConfig),
                    bucket: event.target.value as TimeseriesWidgetConfig["bucket"],
                  }))
                }
                style={{ height: "2.5rem", borderRadius: "0.5rem", border: "1px solid var(--border-subtle)", background: "var(--bg-secondary)", padding: "0 0.75rem" }}
              >
                <option value="day">Day</option>
                <option value="week">Week</option>
              </select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              <Label htmlFor="widget-variant">Chart variant</Label>
              <select
                id="widget-variant"
                value={config.chartVariant}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setConfig((prev) => ({
                    ...(prev as TimeseriesWidgetConfig),
                    chartVariant: event.target.value as TimeseriesWidgetConfig["chartVariant"],
                  }))
                }
                style={{ height: "2.5rem", borderRadius: "0.5rem", border: "1px solid var(--border-subtle)", background: "var(--bg-secondary)", padding: "0 0.75rem" }}
              >
                <option value="line">Line</option>
                <option value="bar">Bar</option>
              </select>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem", color: "var(--text-primary)" }}>
              <input
                type="checkbox"
                checked={config.showSourceSplit}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setConfig((prev) => ({
                    ...(prev as TimeseriesWidgetConfig),
                    showSourceSplit: event.target.checked,
                  }))
                }
              />
              Show source split
            </label>
          </>
        )}

        {"limit" in config && (
          <>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              <Label htmlFor="widget-limit">Limit</Label>
              <Input
                id="widget-limit"
                type="number"
                min={1}
                max={20}
                value={config.limit}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setConfig((prev) => ({
                    ...(prev as TopActivityWidgetConfig),
                    limit: Math.max(1, Math.min(20, Number(event.target.value) || 5)),
                  }))
                }
              />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              <Label htmlFor="widget-mode">Mode</Label>
              <select
                id="widget-mode"
                value={config.mode}
                onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                  setConfig((prev) => ({
                    ...(prev as TopActivityWidgetConfig),
                    mode: event.target.value as TopActivityWidgetConfig["mode"],
                  }))
                }
                style={{ height: "2.5rem", borderRadius: "0.5rem", border: "1px solid var(--border-subtle)", background: "var(--bg-secondary)", padding: "0 0.75rem" }}
              >
                <option value="both">Users + Conversations</option>
                <option value="users">Users only</option>
                <option value="conversations">Conversations only</option>
              </select>
            </div>
          </>
        )}
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
        <Button onClick={() => onSave(config)}>Save</Button>
      </DialogFooter>
    </>
  );
}
