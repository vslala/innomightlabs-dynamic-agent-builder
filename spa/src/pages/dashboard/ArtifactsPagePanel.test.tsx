import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "../../components/ui/checkbox";
import { Button } from "../../components/ui/button";
import type { ArtifactResponse } from "../../services/artifacts";
import { ArtifactsPagePanel, type ArtifactsPagePanelProps } from "./ArtifactsPagePanel";

const artifact: ArtifactResponse = {
  artifact_id: "artifact-1", artifact_type: "html_report", title: "Weekly report", filename: "report.html",
  mime_type: "text/html", size_bytes: 1024, source: { metadata: {} }, created_at: "2026-10-01T12:00:00Z", view_url: "https://example.com/report",
};
function props(overrides: Partial<ArtifactsPagePanelProps> = {}): ArtifactsPagePanelProps {
  return { artifacts: [artifact], selected: [], loading: false, error: null, locked: false, notification: null,
    onReload: vi.fn(), onDismiss: vi.fn(), onSelectionChange: vi.fn(), onDelete: vi.fn(), onBulkDelete: vi.fn(), ...overrides };
}
function markup(overrides: Partial<ArtifactsPagePanelProps> = {}) {
  return renderToStaticMarkup(<MemoryRouter><ArtifactsPagePanel {...props(overrides)} /></MemoryRouter>);
}
function elements(node: React.ReactNode): React.ReactElement<Record<string, unknown>>[] {
  if (!React.isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...React.Children.toArray(node.props.children as React.ReactNode).flatMap(elements)];
}
function checkboxNodes(p: ArtifactsPagePanelProps) {
  return elements(ArtifactsPagePanel(p)).filter((node) => node.type === Checkbox) as React.ReactElement<React.ComponentProps<typeof Checkbox>>[];
}
function buttonNodes(p: ArtifactsPagePanelProps) {
  return elements(ArtifactsPagePanel(p)).filter((node) => node.type === Button) as React.ReactElement<React.ComponentProps<typeof Button>>[];
}

describe("artifacts panel markup and direct handlers (not browser interaction)", () => {
  it("uses labeled row controls and preserves the existing open link", () => {
    const html = markup();
    expect(html).toContain("Select all loaded artifacts");
    expect(html).toContain('aria-label="Select artifact: Weekly report"');
    expect(html).toContain('aria-label="Delete artifact: Weekly report"');
    expect(html).toContain('href="/dashboard/artifacts/artifact-1"');
    expect(html).toContain('dateTime="2026-10-01T12:00:00Z"');
    expect(html).toContain("0 selected");
    expect(html).not.toContain("Download");
  });

  it("sets native indeterminate through the shared ref and selects/clears loaded IDs", () => {
    const p = props({ artifacts: [artifact, { ...artifact, artifact_id: "artifact-2" }], selected: [artifact.artifact_id] });
    expect(markup(p)).toContain('aria-checked="mixed"');
    const top = checkboxNodes(p)[0];
    const input = { indeterminate: false } as HTMLInputElement;
    if (typeof top.props.ref === "function") top.props.ref(input);
    expect(input.indeterminate).toBe(true);
    top.props.onChange?.({ currentTarget: { checked: true } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["artifact-1", "artifact-2"]);
    top.props.onChange?.({ currentTarget: { checked: false } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith([]);
  });

  it("row handlers select and deselect without a nested clickable card", () => {
    const p = props();
    checkboxNodes(p)[1].props.onChange?.({ currentTarget: { checked: true } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenCalledExactlyOnceWith([artifact.artifact_id]);
    const selected = props({ selected: [artifact.artifact_id] });
    checkboxNodes(selected)[1].props.onChange?.({ currentTarget: { checked: false } } as React.ChangeEvent<HTMLInputElement>);
    expect(selected.onSelectionChange).toHaveBeenCalledExactlyOnceWith([]);
  });

  it("routes row delete and bulk delete to confirmation handlers, not HTTP", () => {
    const p = props({ selected: [artifact.artifact_id] });
    const buttons = buttonNodes(p);
    buttons.find((button) => button.props["aria-label"] === "Delete artifact: Weekly report")?.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    buttons.find((button) => React.Children.toArray(button.props.children).includes("Delete selected"))?.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    expect(p.onDelete).toHaveBeenCalledExactlyOnceWith(artifact);
    expect(p.onBulkDelete).toHaveBeenCalledOnce();
  });

  it.each([{ locked: true }, { loading: true }])("disables and guards selection, deletion, reload and retry while busy: %s", (busy) => {
    const p = props({ ...busy, error: "Reload unavailable", selected: [artifact.artifact_id] });
    for (const checkbox of checkboxNodes(p)) {
      expect(checkbox.props.disabled).toBe(true);
      checkbox.props.onChange?.({ currentTarget: { checked: true } } as React.ChangeEvent<HTMLInputElement>);
    }
    for (const button of buttonNodes(p)) {
      expect(button.props.disabled).toBe(true);
      button.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    }
    expect(p.onSelectionChange).not.toHaveBeenCalled();
    expect(p.onDelete).not.toHaveBeenCalled();
    expect(p.onBulkDelete).not.toHaveBeenCalled();
    expect(p.onReload).not.toHaveBeenCalled();
  });

  it("renders loading, retryable error and empty states with primitives", () => {
    expect(markup({ artifacts: [], loading: true })).toContain("Loading artifacts");
    const error = markup({ artifacts: [], error: "Please retry" });
    expect(error).toContain('role="alert"');
    expect(error).toContain("Retry</button>");
    expect(error).not.toContain("No artifacts yet");
    expect(markup({ artifacts: [] })).toContain("No artifacts yet");
  });

  it("keeps dismissible success visible after removing the last artifact and announces errors", () => {
    const p = props({ artifacts: [], notification: { variant: "success", message: "1 deleted, 0 failed." } });
    const html = markup(p);
    expect(html).toContain("No artifacts yet");
    expect(html).toContain("1 deleted, 0 failed.");
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    buttonNodes(p).find((button) => button.props["aria-label"] === "Dismiss notification")?.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
    expect(p.onDismiss).toHaveBeenCalledOnce();
    expect(markup({ notification: { variant: "error", message: "0 deleted, 1 failed." } })).toContain('aria-live="assertive"');
  });
});
