import type { CSSProperties, ReactNode } from "react";

interface AccordionPanelProps {
  title: ReactNode;
  subtitle?: ReactNode;
  trailing?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  style?: CSSProperties;
  summaryStyle?: CSSProperties;
  bodyStyle?: CSSProperties;
}

export function AccordionPanel({
  title,
  subtitle,
  trailing,
  children,
  defaultOpen = true,
  style,
  summaryStyle,
  bodyStyle,
}: AccordionPanelProps) {
  return (
    <details
      open={defaultOpen}
      style={{
        border: "1px solid var(--border-subtle)",
        borderRadius: "0.625rem",
        backgroundColor: "rgba(255,255,255,0.035)",
        overflow: "hidden",
        ...style,
      }}
    >
      <summary
        style={{
          display: "grid",
          gridTemplateColumns: trailing ? "minmax(0, 1fr) auto" : "minmax(0, 1fr)",
          gap: "0.75rem",
          alignItems: "center",
          padding: "0.625rem 0.75rem",
          cursor: "pointer",
          listStyle: "none",
          ...summaryStyle,
        }}
      >
        {subtitle ? (
          <span style={{ minWidth: 0, display: "grid", gap: "0.125rem" }}>
            <span style={{ minWidth: 0 }}>{title}</span>
            <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>{subtitle}</span>
          </span>
        ) : (
          title
        )}
        {trailing && <span>{trailing}</span>}
      </summary>
      <div style={{ padding: "0 0.75rem 0.75rem", ...bodyStyle }}>{children}</div>
    </details>
  );
}
