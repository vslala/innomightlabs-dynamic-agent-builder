import { GripVertical, RefreshCw, Settings, Trash2, TriangleAlert } from "lucide-react";

import { Button } from "../../../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../../../components/ui/card";

interface AnalyticsWidgetFrameProps {
  title: string;
  children: React.ReactNode;
  onRefresh?: () => void;
  onConfigure?: () => void;
  onRemove?: () => void;
  removable?: boolean;
  truncated?: boolean;
}

export function AnalyticsWidgetFrame({
  title,
  children,
  onRefresh,
  onConfigure,
  onRemove,
  removable = true,
  truncated = false,
}: AnalyticsWidgetFrameProps) {
  return (
    <Card style={{ height: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <CardHeader style={{ paddingBottom: "0.75rem" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <div
              className="analytics-widget-drag-handle"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-muted)",
                cursor: "grab",
              }}
            >
              <GripVertical className="h-4 w-4" />
            </div>
            <CardTitle className="text-base" style={{ fontSize: "1rem", lineHeight: 1.2 }}>
              {title}
            </CardTitle>
            {truncated && (
              <span title="Data truncated by backend guardrails">
                <TriangleAlert className="h-4 w-4 text-amber-400" />
              </span>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
            {onRefresh && (
              <Button variant="ghost" size="icon" onClick={onRefresh} style={{ height: "1.75rem", width: "1.75rem" }}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            )}
            {onConfigure && (
              <Button variant="ghost" size="icon" onClick={onConfigure} style={{ height: "1.75rem", width: "1.75rem" }}>
                <Settings className="h-4 w-4" />
              </Button>
            )}
            {removable && onRemove && (
              <Button variant="ghost" size="icon" onClick={onRemove} style={{ height: "1.75rem", width: "1.75rem", color: "#f87171" }}>
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent style={{ flex: 1, minHeight: 0 }}>{children}</CardContent>
    </Card>
  );
}
