import { useState, type CSSProperties } from "react";

import { Button } from "./button";
import { Label } from "./label";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export function parseMaybeJson(value: string): JsonValue | string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  try {
    return JSON.parse(trimmed) as JsonValue;
  } catch {
    return value;
  }
}

export function normalizeJsonValue(value: unknown): JsonValue | string {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(normalizeJsonValue) as JsonValue[];
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, normalizeJsonValue(item)])
    ) as { [key: string]: JsonValue };
  }
  return String(value);
}

export function jsonValueSummary(value: JsonValue): string {
  if (Array.isArray(value)) return `Array(${value.length})`;
  if (value && typeof value === "object") return `Object(${Object.keys(value).length})`;
  if (value === null) return "null";
  if (typeof value === "string") return "text";
  return String(value);
}

interface JsonTreeViewerProps {
  label?: string;
  value: unknown;
  maxHeight?: string;
}

export function JsonTreeViewer({ label, value, maxHeight = "28rem" }: JsonTreeViewerProps) {
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(new Set());
  const normalized = normalizeJsonValue(value);
  const parsed = typeof normalized === "string" ? parseMaybeJson(normalized) : normalized;
  const displayValue = typeof parsed === "string" ? parsed : parsed;

  const togglePath = (path: string) => {
    setCollapsedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  return (
    <div style={treeStyle}>
      <div style={headerStyle}>
        {label ? <Label>{label}</Label> : <span />}
        <div style={actionsStyle}>
          <Button variant="ghost" size="sm" onClick={() => setCollapsedPaths(new Set())}>
            Expand
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setCollapsedPaths(collectCollapsiblePaths(displayValue))}>
            Collapse
          </Button>
        </div>
      </div>
      <div style={{ ...bodyStyle, maxHeight }}>
        <JsonTreeNode
          name={null}
          value={displayValue}
          path="$"
          depth={0}
          collapsedPaths={collapsedPaths}
          onToggle={togglePath}
        />
      </div>
    </div>
  );
}

export function JsonViewer({ value }: { value: unknown }) {
  return <JsonTreeViewer value={value} />;
}

function collectCollapsiblePaths(value: unknown, path = "$", paths = new Set<string>()): Set<string> {
  if (!isJsonBranch(value)) {
    return paths;
  }

  paths.add(path);
  const entries = Array.isArray(value) ? value.map((item, index) => [String(index), item] as const) : Object.entries(value);
  entries.forEach(([key, child]) => collectCollapsiblePaths(child, `${path}.${key}`, paths));
  return paths;
}

function isJsonBranch(value: unknown): value is Record<string, unknown> | unknown[] {
  return typeof value === "object" && value !== null && (Array.isArray(value) || Object.keys(value).length > 0);
}

function JsonTreeNode({
  name,
  value,
  path,
  depth,
  collapsedPaths,
  onToggle,
}: {
  name: string | null;
  value: unknown;
  path: string;
  depth: number;
  collapsedPaths: Set<string>;
  onToggle: (path: string) => void;
}) {
  const isArray = Array.isArray(value);
  const isBranch = isJsonBranch(value);
  const isCollapsed = collapsedPaths.has(path);
  const entries = isBranch
    ? isArray
      ? value.map((item, index) => [String(index), item] as const)
      : Object.entries(value)
    : [];
  const summary = isArray ? `Array(${entries.length})` : `Object(${entries.length})`;

  if (!isBranch) {
    return (
      <div style={{ ...lineStyle, paddingLeft: `${depth}rem` }}>
        {name !== null && <span style={keyStyle}>"{name}": </span>}
        <JsonPrimitive value={value} />
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        style={{ ...lineStyle, ...buttonLineStyle, paddingLeft: `${depth}rem` }}
        onClick={() => onToggle(path)}
      >
        <span style={twistyStyle}>{isCollapsed ? "+" : "-"}</span>
        {name !== null && <span style={keyStyle}>"{name}": </span>}
        <span style={braceStyle}>{isArray ? "[" : "{"}</span>
        {isCollapsed && <span style={summaryStyle}>{summary}</span>}
        {isCollapsed && <span style={braceStyle}>{isArray ? "]" : "}"}</span>}
      </button>
      {!isCollapsed && (
        <>
          {entries.map(([key, child]) => (
            <JsonTreeNode
              key={`${path}.${key}`}
              name={key}
              value={child}
              path={`${path}.${key}`}
              depth={depth + 1}
              collapsedPaths={collapsedPaths}
              onToggle={onToggle}
            />
          ))}
          <div style={{ ...lineStyle, paddingLeft: `${depth}rem` }}>
            <span style={braceStyle}>{isArray ? "]" : "}"}</span>
          </div>
        </>
      )}
    </div>
  );
}

function JsonPrimitive({ value }: { value: unknown }) {
  if (typeof value === "string") {
    return <span style={stringStyle}>{JSON.stringify(value)}</span>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span style={literalStyle}>{String(value)}</span>;
  }
  if (value === null) {
    return <span style={nullStyle}>null</span>;
  }
  return <span style={literalStyle}>{JSON.stringify(value)}</span>;
}

export const jsonPayloadShellStyle: CSSProperties = {
  maxWidth: "100%",
  minWidth: 0,
};

const treeStyle: CSSProperties = {
  display: "grid",
  gap: "0.45rem",
  minWidth: 0,
};

const headerStyle: CSSProperties = {
  alignItems: "center",
  display: "flex",
  justifyContent: "space-between",
  gap: "1rem",
};

const actionsStyle: CSSProperties = {
  display: "flex",
  gap: "0.35rem",
};

const bodyStyle: CSSProperties = {
  background: "#121226",
  border: "1px solid rgba(102, 126, 234, 0.28)",
  borderRadius: "0.5rem",
  color: "#e5e7eb",
  fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
  fontSize: "0.76rem",
  lineHeight: 1.55,
  overflow: "auto",
  padding: "0.65rem 0.75rem",
};

const lineStyle: CSSProperties = {
  alignItems: "flex-start",
  display: "flex",
  gap: "0.25rem",
  minHeight: "1.2rem",
  whiteSpace: "pre",
};

const buttonLineStyle: CSSProperties = {
  background: "transparent",
  border: 0,
  color: "inherit",
  cursor: "pointer",
  font: "inherit",
  paddingBottom: 0,
  paddingRight: 0,
  paddingTop: 0,
  textAlign: "left",
  width: "100%",
};

const twistyStyle: CSSProperties = {
  color: "var(--gradient-start)",
  display: "inline-block",
  width: "0.75rem",
};

const keyStyle: CSSProperties = {
  color: "#93c5fd",
};

const stringStyle: CSSProperties = {
  color: "#86efac",
  overflowWrap: "anywhere",
  whiteSpace: "pre-wrap",
};

const literalStyle: CSSProperties = {
  color: "#fbbf24",
};

const nullStyle: CSSProperties = {
  color: "#c4b5fd",
};

const braceStyle: CSSProperties = {
  color: "#e5e7eb",
};

const summaryStyle: CSSProperties = {
  color: "var(--text-muted)",
  marginLeft: "0.35rem",
};
