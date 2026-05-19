import { useState } from "react";

import { Button, Label, Textarea } from "../../../../components/ui";

export function AutomationJsonEditor({
  label,
  value,
  error,
  readOnly = false,
  minHeight = "10rem",
  onChange,
  onFormat,
}: {
  label: string;
  value: string;
  error?: string | null;
  readOnly?: boolean;
  minHeight?: string;
  onChange?: (value: string) => void;
  onFormat?: () => void;
}) {
  return (
    <div className="automation-json-editor">
      <div className="automation-json-editor__header">
        <Label>{label}</Label>
        {onFormat && (
          <Button variant="ghost" size="sm" onClick={onFormat} disabled={readOnly}>
            Format
          </Button>
        )}
      </div>
      <Textarea
        className="automation-json-editor__textarea"
        value={value}
        readOnly={readOnly}
        onChange={(event) => onChange?.(event.target.value)}
        spellCheck={false}
        style={{ minHeight }}
      />
      {error && <div className="automation-json-editor__error">{error}</div>}
    </div>
  );
}

export function AutomationJsonTreeViewer({ label, value }: { label: string; value: unknown }) {
  const [collapsedPaths, setCollapsedPaths] = useState<Set<string>>(new Set());

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
    <div className="automation-json-tree">
      <div className="automation-json-tree__header">
        <Label>{label}</Label>
        <div className="automation-json-tree__actions">
          <Button variant="ghost" size="sm" onClick={() => setCollapsedPaths(new Set())}>
            Expand
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCollapsedPaths(collectCollapsiblePaths(value))}
          >
            Collapse
          </Button>
        </div>
      </div>
      <div className="automation-json-tree__body">
        <JsonTreeNode
          name={null}
          value={value}
          path="$"
          depth={0}
          collapsedPaths={collapsedPaths}
          onToggle={togglePath}
        />
      </div>
    </div>
  );
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
      <div className="automation-json-tree__line" style={{ paddingLeft: `${depth}rem` }}>
        {name !== null && <span className="automation-json-tree__key">"{name}": </span>}
        <JsonPrimitive value={value} />
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        className="automation-json-tree__line automation-json-tree__line--button"
        style={{ paddingLeft: `${depth}rem` }}
        onClick={() => onToggle(path)}
      >
        <span className="automation-json-tree__twisty">{isCollapsed ? "+" : "-"}</span>
        {name !== null && <span className="automation-json-tree__key">"{name}": </span>}
        <span className="automation-json-tree__brace">{isArray ? "[" : "{"}</span>
        {isCollapsed && <span className="automation-json-tree__summary">{summary}</span>}
        {isCollapsed && <span className="automation-json-tree__brace">{isArray ? "]" : "}"}</span>}
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
          <div className="automation-json-tree__line" style={{ paddingLeft: `${depth}rem` }}>
            <span className="automation-json-tree__brace">{isArray ? "]" : "}"}</span>
          </div>
        </>
      )}
    </div>
  );
}

function JsonPrimitive({ value }: { value: unknown }) {
  if (typeof value === "string") {
    return <span className="automation-json-tree__string">"{value}"</span>;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return <span className="automation-json-tree__literal">{String(value)}</span>;
  }
  if (value === null) {
    return <span className="automation-json-tree__null">null</span>;
  }
  return <span className="automation-json-tree__literal">{JSON.stringify(value)}</span>;
}
