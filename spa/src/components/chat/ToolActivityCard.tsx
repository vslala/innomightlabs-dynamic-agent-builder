import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { AccordionPanel, Card, JsonTreeViewer, jsonPayloadShellStyle, jsonValueSummary, normalizeJsonValue, parseMaybeJson } from "../ui";
import type { ToolActivity } from "../../types/message";
import type { JsonValue } from "../ui";

export function ToolActivityCard({ activity }: { activity: ToolActivity }) {
  const resultPayload = parseMaybeJson(activity.content);
  const statusColor =
    activity.status === "running" ? "var(--gradient-start)" : activity.status === "success" ? "#22c55e" : "#ef4444";
  const StatusIcon = activity.status === "running" ? Loader2 : activity.status === "success" ? CheckCircle2 : XCircle;

  return (
    <Card style={{ overflow: "hidden", backgroundColor: "rgba(255,255,255,0.035)" }}>
      <AccordionPanel
        defaultOpen={activity.status === "running"}
        style={{ border: 0, borderRadius: 0, backgroundColor: "transparent" }}
        summaryStyle={{
          gridTemplateColumns: "auto auto minmax(0, 1fr) auto",
          gap: "0.5rem",
        }}
        title={
          <>
            <StatusIcon
              style={{
                height: "0.95rem",
                width: "0.95rem",
                color: statusColor,
                animation: activity.status === "running" ? "spin 1s linear infinite" : undefined,
              }}
            />
            <span style={{ fontFamily: "monospace", fontSize: "0.75rem", color: "var(--text-muted)" }}>
              {activity.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <span style={{ color: "var(--text-primary)", fontWeight: 600, minWidth: 0 }}>
              {activity.tool_name.replace(/_/g, " ")}
            </span>
          </>
        }
        trailing={
          <span style={{ color: statusColor, fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase" }}>
            {activity.status}
          </span>
        }
      >
        <div style={{ display: "grid", gap: "0.625rem" }}>
          {activity.tool_args && Object.keys(activity.tool_args).length > 0 && (
            <PayloadSection title="Arguments" value={activity.tool_args} />
          )}
          {activity.status === "running" ? (
            <div style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>{activity.content}</div>
          ) : (
            <PayloadSection title="Result" value={resultPayload} />
          )}
        </div>
      </AccordionPanel>
    </Card>
  );
}

function PayloadSection({ title, value }: { title: string; value: unknown }) {
  const summary =
    typeof value === "string"
      ? "text"
      : jsonValueSummary(normalizeJsonValue(value) as JsonValue);

  return (
    <AccordionPanel
      defaultOpen
      style={{
        border: 0,
        borderTop: "1px solid var(--border-subtle)",
        borderRadius: 0,
        backgroundColor: "transparent",
      }}
      summaryStyle={{ padding: "0.625rem 0 0.375rem" }}
      bodyStyle={{ padding: 0 }}
      title={<span style={{ color: "var(--text-primary)", fontWeight: 700 }}>{title}</span>}
      subtitle={<span>{summary}</span>}
    >
      <div style={jsonPayloadShellStyle}>
        <JsonTreeViewer value={value} maxHeight="22rem" />
      </div>
    </AccordionPanel>
  );
}
