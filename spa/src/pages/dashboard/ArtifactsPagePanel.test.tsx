import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Checkbox } from "../../components/ui/checkbox";
import { Button } from "../../components/ui/button";
import type { ArtifactResponse } from "../../services/artifacts";
import { ArtifactsPageContent, ArtifactsPagePanel, type ArtifactsPagePanelProps } from "./ArtifactsPagePanel";
import { INITIAL_ARTIFACT_LIBRARY_STATE, type ArtifactLibraryState } from "./artifactLibrary";
import type { ArtifactSourceNames } from "./artifactSources";
import { SearchInput } from "../../components/ui/search-input";

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
type ContentProps = React.ComponentProps<typeof ArtifactsPageContent>;
function contentProps(overrides: Partial<ContentProps> = {}): ContentProps {
  return { ...props(), view: { ...INITIAL_ARTIFACT_LIBRARY_STATE }, onViewChange: vi.fn(), ...overrides };
}
function contentMarkup(p: ContentProps) {
  return renderToStaticMarkup(<MemoryRouter><ArtifactsPageContent {...p} /></MemoryRouter>);
}
function checkboxNodes(p: ArtifactsPagePanelProps, view: ArtifactLibraryState = INITIAL_ARTIFACT_LIBRARY_STATE) {
  return elements(ArtifactsPageContent(contentProps({ ...p, view }))).filter((node) => node.type === Checkbox) as React.ReactElement<React.ComponentProps<typeof Checkbox>>[];
}
function buttonNodes(p: ArtifactsPagePanelProps, view: ArtifactLibraryState = INITIAL_ARTIFACT_LIBRARY_STATE) {
  return elements(ArtifactsPageContent(contentProps({ ...p, view }))).filter((node) => node.type === Button) as React.ReactElement<React.ComponentProps<typeof Button>>[];
}
function click(button: React.ReactElement<React.ComponentProps<typeof Button>> | undefined) {
  expect(button).toBeDefined();
  button!.props.onClick?.({} as React.MouseEvent<HTMLButtonElement>);
}

describe("artifacts panel markup and direct handlers (not browser interaction)", () => {
  it("uses labeled row controls and preserves the existing open link", () => {
    const html = markup();
    expect(html).toContain("Select visible artifacts");
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
    click(buttons.find((button) => button.props["aria-label"] === "Delete artifact: Weekly report"));
    click(buttons.find((button) => React.Children.toArray(button.props.children).includes("Delete selected")));
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

  it("does not bulk delete without a selection", () => {
    const p = props();
    const bulk = buttonNodes(p).find((button) => React.Children.toArray(button.props.children).includes("Delete selected"));
    expect(bulk?.props.disabled).toBe(true);
    click(bulk);
    expect(p.onBulkDelete).not.toHaveBeenCalled();
  });
});

const sourceNames: ArtifactSourceNames = {
  agents: { researcher: "Research assistant" }, automations: { digest: "Morning digest" },
  conversations: { planning: "Quarterly planning" }, skills: { reports: "Report builder" },
};
const sourcedArtifact: ArtifactResponse = {
  ...artifact, source: { metadata: {}, agent_id: "researcher", automation_id: "digest", conversation_id: "planning",
    skill_id: "reports", automation_run_id: "run-12345678901234567890", automation_node_id: "node-12345678901234567890", message_id: "message-12345678901234567890" },
};
function view(overrides: Partial<ArtifactLibraryState> = {}): ArtifactLibraryState {
  return { ...INITIAL_ARTIFACT_LIBRARY_STATE, ...overrides };
}
function detailTitles(p: ContentProps): string[] {
  return elements(ArtifactsPageContent(p)).filter((node) => node.type === Button && typeof node.props["aria-label"] === "string" && node.props["aria-label"].startsWith("Show details:"))
    .map((node) => node.props["aria-label"] as string);
}
function activeTitles(p: ContentProps): string[] {
  return buttonNodes(p, p.view).filter((button) => button.props["aria-pressed"] === true && button.props["aria-label"]?.startsWith("Show details:"))
    .map((button) => button.props["aria-label"]!);
}

const formatCases = [
  ["html_report", "HTML report", "HTML reports"], ["image", "Image", "Images"], ["file", "File", "Files"],
  ["csv", "CSV", "CSV"], ["markdown", "Markdown", "Markdown"], ["json", "JSON", "JSON"],
  ["text", "Text", "Text"], ["code", "Code", "Code"], ["canvas", "Canvas", "Canvases"],
] as const;
function groupNodes(p: ContentProps) {
  return elements(ArtifactsPageContent(p)).filter((node) => node.type === "details");
}
function clickSummary(group: React.ReactElement<Record<string, unknown>>) {
  const summary = elements(group).find((node) => node.type === "summary") as React.ReactElement<React.ComponentProps<"summary">>;
  expect(summary).toBeDefined();
  const preventDefault = vi.fn();
  summary.props.onClick?.({ preventDefault } as unknown as React.MouseEvent<HTMLElement>);
  expect(preventDefault).toHaveBeenCalledOnce();
}

describe("controlled artifact library content (SSR and direct callbacks)", () => {
  it.each(formatCases)("displays and filters %s with row/inspector label %s", (format, label, optionLabel) => {
    const artifacts = formatCases.map(([artifact_type]) => ({ ...artifact, artifact_type, artifact_id: artifact_type, title: `Output ${artifact_type}` }));
    const p = contentProps({ artifacts, view: view({ format }) });
    expect(detailTitles(p)).toEqual([`Show details: Output ${format}`]);
    const html = contentMarkup(p);
    expect(html).toContain("1 of 9 loaded");
    expect(html).toContain(`${label} · 1.0 KB`);
    expect(html).toContain(`<h2>Artifact details</h2><span>${label}</span>`);
    expect(html).not.toContain("undefined");
    const control = elements(ArtifactsPageContent(p)).find((node) => node.props.label === "Artifact format") as React.ReactElement<{
      options: readonly (readonly [string, string])[]; onChange: (value: string) => void;
    }>;
    expect(control.props.options).toContainEqual([format, optionLabel]);
    control.props.onChange(format);
    expect(p.onViewChange).toHaveBeenCalledExactlyOnceWith({ format });
    expect(detailTitles({ ...p, view: view() })).toHaveLength(9);
  });

  it.each([
    ["html_report", "report.HTML", "application/octet-stream", "HTML"],
    ["image", "chart.png", "application/octet-stream", "PNG"],
    ["file", "export.csv", "application/octet-stream", "CSV"],
    ["image", "chart", "image/png", "PNG"],
    ["file", "export", "text/csv; charset=utf-8", "CSV"],
    ["image", "photo.jpeg", "image/jpeg", "JPG"],
    ["image", "unknown", "application/octet-stream", "IMG"],
  ] as const)("renders %s %s (%s) as a labeled %s document tile, not a content preview", (artifact_type, filename, mime_type, label) => {
    const html = contentMarkup(contentProps({ artifacts: [{ ...artifact, artifact_type, filename, mime_type }] }));
    const tiles = [...html.matchAll(/<span[^>]*role="img" aria-label="([^"]+)"[^>]*>(.*?)<\/span><\/span>/g)];
    expect(tiles).toHaveLength(3); // Row plus inline/mobile and desktop inspectors.
    for (const tile of tiles) {
      expect(tile[1]).toBe(`${label} file`);
      expect(tile[2]).toBe(`<span>${label}`);
      expect(tile[0]).not.toContain("<svg");
    }
    const covers = [...html.matchAll(/<div[^>]*aria-label="File format summary"[^>]*>(.*?)<\/div>/g)];
    expect(covers).toHaveLength(2);
    for (const cover of covers) {
      expect(cover[1]).toContain(`aria-label="${label} file"`);
      expect(cover[1]).toContain(`<span>${label} · 1.0 KB</span>`);
      expect(cover[1]).not.toMatch(/<svg|<img|<iframe|<canvas|<video|<object|<embed|https?:/);
    }
    expect(html).not.toMatch(/<img|<iframe|<canvas|<video|<object|<embed|content preview/i);
    expect(html).not.toContain(artifact.view_url!);
    if (label !== "PNG") expect(html).not.toContain('aria-label="PNG file"');
  });

  it("renders colored agent initials from sourceNames with a stable tone across renaming and regrouping", () => {
    const p = contentProps({ artifacts: [sourcedArtifact], sourceNames });
    const avatar = (html: string) => /<summary[^>]*><span[^>]*data-tone="(blue|purple|green)" aria-hidden="true">([^<]+)<\/span>/.exec(html);
    const initial = avatar(contentMarkup(p));
    expect(initial).not.toBeNull();
    expect(initial?.[2]).toBe("RA");
    const renamedNames = { ...sourceNames, agents: { researcher: "Data scientist" } };
    const renamed = avatar(contentMarkup({ ...p, sourceNames: renamedNames, view: view({ sort: "name", query: "Weekly" }) }));
    expect(renamed?.[2]).toBe("DS");
    expect(renamed?.[1]).toBe(initial?.[1]);
    contentMarkup({ ...p, view: view({ group: "automation" }) });
    expect(avatar(contentMarkup({ ...p, view: view({ group: "agent" }) }))?.slice(1)).toEqual(initial?.slice(1));
  });

  it("starts Technical details closed and retains MIME and every full recorded ID inside each inspector", () => {
    const fullId = (kind: string) => `${kind}-123456789012345678901234567890-full`;
    const file: ArtifactResponse = { ...sourcedArtifact, artifact_id: fullId("artifact"), source: { metadata: {},
      agent_id: fullId("agent"), automation_id: fullId("automation"), automation_run_id: fullId("run"),
      automation_node_id: fullId("node"), conversation_id: fullId("conversation"), message_id: fullId("message"), skill_id: fullId("skill") } };
    const html = contentMarkup(contentProps({ artifacts: [file], sourceNames }));
    const disclosures = [...html.matchAll(/<details([^>]*)><summary>Technical details[\s\S]*?<\/details>/g)];
    expect(disclosures).toHaveLength(2);
    for (const disclosure of disclosures) {
      expect(disclosure[1]).not.toMatch(/\bopen(?:\s|=|$)/);
      expect(disclosure[0]).toContain(`<dt>Content type</dt><dd>${file.mime_type}</dd>`);
      for (const [label, id] of [
        ["Artifact ID", file.artifact_id], ["Agent ID", file.source.agent_id], ["Automation ID", file.source.automation_id],
        ["Automation run", file.source.automation_run_id], ["Workflow step ID", file.source.automation_node_id],
        ["Conversation ID", file.source.conversation_id], ["Message ID", file.source.message_id], ["Skill ID", file.source.skill_id],
      ]) {
        expect(disclosure[0]).toContain(`<dt>${label}</dt><dd><code`);
        expect(disclosure[0]).toContain(`>${id}</code></dd>`);
      }
    }
    const mainSummary = html.replace(/<details[^>]*><summary>Technical details[\s\S]*?<\/details>/g, "");
    expect(mainSummary).toContain("Where this came from");
    expect(mainSummary).not.toMatch(/<dt>Content type<\/dt>|<code/);
  });

  it("renders an unknown runtime artifact kind as a generic File without undefined classes or previews", () => {
    const unknown = { ...artifact, artifact_type: "future_kind" as ArtifactResponse["artifact_type"] };
    const p = contentProps({ artifacts: [unknown] });
    const html = contentMarkup(p);
    expect(html).toContain("File · 1.0 KB");
    expect(html).toContain("<h2>Artifact details</h2><span>File</span>");
    expect(html).not.toMatch(/undefined|<img|<iframe|<canvas|<object|<embed/);
    expect(detailTitles({ ...p, view: view({ format: "file" }) })).toEqual([]);
    expect(contentMarkup({ ...p, view: view({ format: "file" }) })).toContain("No matching artifacts");
  });

  it.each([
    ["agent", "agent:agent:researcher"], ["automation", "automation:automation:digest"], ["none", "none:all"],
  ] as const)("controls %s collapse through partial summary updates without mutating state", (group, key) => {
    const preserved = "agent:agent:unrelated";
    const p = contentProps({ artifacts: [sourcedArtifact], view: view({ group, collapsedGroups: [preserved] }) });
    expect(groupNodes(p)[0].props.open).toBe(true);
    clickSummary(groupNodes(p)[0]);
    expect(p.onViewChange).toHaveBeenCalledExactlyOnceWith({ collapsedGroups: [preserved, key] });
    expect(p.view.collapsedGroups).toEqual([preserved]);
    expect(groupNodes(p)[0].props.open).toBe(true);
    const collapsed = { ...p, view: { ...p.view, collapsedGroups: [preserved, key] } };
    expect(groupNodes(collapsed)[0].props.open).toBe(false);
    expect(contentMarkup(collapsed)).not.toMatch(/<details[^>]*\bopen=/);
    clickSummary(groupNodes(collapsed)[0]);
    expect(p.onViewChange).toHaveBeenLastCalledWith({ collapsedGroups: [preserved] });
    expect(collapsed.view.collapsedGroups).toEqual([preserved, key]);
    expect(p.onSelectionChange).not.toHaveBeenCalled();
    expect(p.onDelete).not.toHaveBeenCalled();
  });

  it("keeps collapse state keyed by IDs despite equal names, renaming, sorting, filtering and regrouping", () => {
    const other = { ...sourcedArtifact, artifact_id: "other", title: "Another report", source: { ...sourcedArtifact.source, agent_id: "other-agent" } };
    const p = contentProps({ artifacts: [sourcedArtifact, other], sourceNames: { ...sourceNames, agents: { researcher: "Same name", "other-agent": "Same name" } },
      view: view({ collapsedGroups: ["agent:agent:researcher"] }) });
    expect(groupNodes(p).map((node) => node.props.open)).toEqual([false, true]);
    expect(groupNodes({ ...p, view: { ...p.view, sort: "name" } }).map((node) => node.props.open)).toEqual([true, false]);
    expect(groupNodes({ ...p, sourceNames: { ...sourceNames, agents: { researcher: "Renamed" } } }).map((node) => node.props.open)).toEqual([false, true]);
    expect(groupNodes({ ...p, view: { ...p.view, query: "Weekly" } }).map((node) => node.props.open)).toEqual([false]);
    expect(groupNodes({ ...p, view: { ...p.view, group: "automation" } }).map((node) => node.props.open)).toEqual([true]);
    clickSummary(groupNodes(p)[1]);
    expect(p.onViewChange).toHaveBeenLastCalledWith({ collapsedGroups: ["agent:agent:researcher", "agent:agent:other-agent"] });
    expect(p.view.collapsedGroups).toEqual(["agent:agent:researcher"]);
  });

  it.each([{ locked: true }, { loading: true }])("prevents native summary toggling and guards collapse updates while busy: %s", (busy) => {
    for (const collapsedGroups of [[], ["agent:agent:researcher"]]) {
      const p = contentProps({ ...busy, artifacts: [sourcedArtifact], view: view({ collapsedGroups }) });
      clickSummary(groupNodes(p)[0]);
      expect(p.onViewChange).not.toHaveBeenCalled();
      expect(groupNodes(p)[0].props.open).toBe(collapsedGroups.length === 0);
      expect(p.view.collapsedGroups).toEqual(collapsedGroups);
    }
  });

  it("reconciles the inspector to expanded groups, hides it when all collapse, and restores the controlled active ID on expansion", () => {
    const other = { ...artifact, artifact_id: "other", title: "Other report", source: { metadata: {}, agent_id: "other-agent" } };
    const p = contentProps({ artifacts: [sourcedArtifact, other], view: view({ activeId: sourcedArtifact.artifact_id }) });
    expect(activeTitles(p)).toEqual(["Show details: Weekly report"]);
    const collapsed = { ...p, view: { ...p.view, collapsedGroups: ["agent:agent:researcher"] } };
    expect(activeTitles(collapsed)).toEqual(["Show details: Other report"]);
    expect(contentMarkup(collapsed)).toContain('aria-label="Details for Other report"');
    expect(contentMarkup(collapsed)).not.toContain('aria-label="Details for Weekly report"');
    expect(activeTitles({ ...collapsed, view: { ...collapsed.view, activeId: null } })).toEqual(["Show details: Other report"]);
    const allCollapsed = { ...collapsed, view: { ...collapsed.view, collapsedGroups: ["agent:agent:researcher", "agent:agent:other-agent"] } };
    expect(activeTitles(allCollapsed)).toEqual([]);
    expect(contentMarkup(allCollapsed)).not.toContain('aria-label="Selected artifact details"');
    expect(contentMarkup(allCollapsed)).not.toContain("Artifact details");
    expect(contentMarkup(allCollapsed)).not.toContain("No matching artifacts");
    expect(activeTitles({ ...collapsed, view: { ...collapsed.view, collapsedGroups: [] } })).toEqual(["Show details: Weekly report"]);
    expect(p.onViewChange).not.toHaveBeenCalled();
  });

  it("includes collapsed groups in select-visible membership, counts and bulk deletion, but excludes filtered-out IDs", () => {
    const other = { ...sourcedArtifact, artifact_id: "other", title: "Other report", source: { ...sourcedArtifact.source, agent_id: "other-agent" } };
    const filteredOut = { ...artifact, artifact_id: "filtered-out", artifact_type: "image" as const };
    const p = contentProps({ artifacts: [sourcedArtifact, other, filteredOut], selected: ["filtered-out", sourcedArtifact.artifact_id],
      view: view({ format: "html_report", collapsedGroups: ["agent:agent:researcher", "agent:agent:other-agent"] }) });
    const html = contentMarkup(p);
    expect(html).toContain("2 of 3 loaded");
    expect(html).toContain("2 selected (1 hidden by filters)");
    const top = checkboxNodes(p, p.view)[0];
    expect(top.props.disabled).toBe(false);
    expect(top.props["aria-checked"]).toBe("mixed");
    top.props.onChange?.({ currentTarget: { checked: true } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["filtered-out", "artifact-1", "other"]);
    const all = { ...p, selected: ["filtered-out", "artifact-1", "other"] };
    const checked = checkboxNodes(all, all.view)[0];
    expect(checked.props.checked).toBe(true);
    checked.props.onChange?.({ currentTarget: { checked: false } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["filtered-out"]);
    click(buttonNodes(p, p.view).find((button) => React.Children.toArray(button.props.children).includes("Delete selected")));
    expect(p.onBulkDelete).toHaveBeenCalledOnce();
    expect(p.selected).toEqual(["filtered-out", "artifact-1"]);
  });
  it("groups by real agent and automation labels and renders linked provenance with full IDs available", () => {
    const p = contentProps({ artifacts: [sourcedArtifact], sourceNames });
    const html = contentMarkup(p);
    expect(html).toContain('aria-label="Research assistant artifacts"');
    for (const [href, label] of [
      ["/dashboard/agents/researcher", "Research assistant"], ["/dashboard/automations/digest", "Morning digest"],
      ["/dashboard/conversations/planning", "Quarterly planning"], ["/dashboard/agents/researcher/skills", "Report builder"],
    ]) {
      expect(html).toContain(`href="${href}"`);
      expect(html).toContain(label);
    }
    for (const [label, id] of [
      ["Automation run", "run-12345678901234567890"],
      ["Workflow step ID", "node-12345678901234567890"],
      ["Message ID", "message-12345678901234567890"],
    ]) {
      expect(html).toContain(`<dt>${label}</dt><dd><code`);
      expect(html).toContain(`>${id}</code></dd>`);
    }
    for (const id of ["researcher", "digest", "planning", "reports", "artifact-1"]) {
      expect(html).toContain(`>${id}</code>`);
    }
    expect(contentMarkup({ ...p, view: view({ group: "automation" }) })).toContain('aria-label="Morning digest artifacts"');
    expect(contentMarkup({ ...p, view: view({ group: "none" }) })).toContain('aria-label="All files artifacts"');
  });

  it("keeps deleted sources identifiable and links encoded IDs without inventing names", () => {
    const deleted: ArtifactResponse = { ...artifact, artifact_id: "file /?", source: { metadata: {},
      agent_id: "deleted /?", automation_id: "deleted-auto", conversation_id: "deleted-chat", skill_id: "deleted-skill" } };
    const html = contentMarkup(contentProps({ artifacts: [deleted] }));
    for (const label of ["Agent · deleted /?", "Automation · deleted-auto", "Conversation · deleted-chat", "Skill · deleted-skill"]) expect(html).toContain(label);
    expect(html).toContain('href="/dashboard/agents/deleted%20%2F%3F"');
    expect(html).toContain('href="/dashboard/artifacts/file%20%2F%3F"');
    expect(html).not.toMatch(/undefined|Unknown agent|Unknown automation/);
  });

  it("renders missing/null source fallbacks without undefined metadata or made-up previews", () => {
    const html = contentMarkup(contentProps({ artifacts: [{ ...artifact, source: { metadata: {}, agent_id: null, skill_id: null, conversation_id: null } }] }));
    for (const label of ["Agent not recorded", "Source not recorded", "Skill not recorded", "report.html", "text/html", "1.0 KB"]) expect(html).toContain(label);
    expect(html).not.toMatch(/undefined|null|<iframe|<img|<canvas|<video|<object|<embed/);
    expect(html).not.toContain(artifact.view_url!);
    expect(html).not.toContain("Automation run");
    expect(html).not.toContain("Message ID");
  });

  it("does not embed image/report contents or offer open links for unavailable files", () => {
    for (const artifact_type of ["image", "html_report", "file"] as const) {
      const html = contentMarkup(contentProps({ artifacts: [{ ...artifact, artifact_type, view_url: null }] }));
      expect(html).not.toMatch(/<img|<iframe|<canvas|<object|<embed/);
      expect(html).not.toContain('href="/dashboard/artifacts/');
      expect(html).not.toContain("Open file");
    }
  });

  it("applies combined search, source, format and date filters before sorting and grouping", () => {
    const clock = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-10-20T12:00:00Z"));
    try {
      const recent = { ...sourcedArtifact, artifact_id: "recent", title: "Alpha report", created_at: "2026-10-19T12:00:00Z" };
      const newer = { ...recent, artifact_id: "newer", title: "Zulu report", created_at: "2026-10-20T12:00:00Z" };
      const old = { ...recent, artifact_id: "old", title: "Old report", created_at: "2026-09-01T12:00:00Z" };
      const image = { ...recent, artifact_id: "image", title: "Image", artifact_type: "image" as const };
      const chat = { ...recent, artifact_id: "chat", title: "Chat report", source: { metadata: {}, agent_id: "researcher", conversation_id: "planning" } };
      const p = contentProps({ artifacts: [newer, image, old, chat, recent], sourceNames,
        view: view({ query: " RESEARCH assistant ", format: "html_report", source: "automation", period: "7", sort: "name", group: "automation" }) });
      expect(detailTitles(p)).toEqual(["Show details: Alpha report", "Show details: Zulu report"]);
      const html = contentMarkup(p);
      expect(html).toContain("2 of 5 loaded");
      expect(html).toContain('aria-label="Morning digest artifacts"');
      expect(html).not.toContain('aria-label="Show details: Old report"');
      expect(html).not.toContain('aria-label="Show details: Image"');
      expect(html).not.toContain('aria-label="Show details: Chat report"');
      expect(detailTitles({ ...p, view: { ...p.view, sort: "newest" } })).toEqual(["Show details: Zulu report", "Show details: Alpha report"]);
      expect(detailTitles({ ...p, view: { ...p.view, source: "conversation" } })).toEqual(["Show details: Chat report"]);
    } finally {
      clock.mockRestore();
    }
  });

  it("shows no-match feedback, disables select-visible, and resets only filter fields", () => {
    const p = contentProps({ view: view({ query: "absent", format: "image", source: "automation", period: "7", group: "none", sort: "name", activeId: artifact.artifact_id }) });
    const html = contentMarkup(p);
    expect(html).toContain("No matching artifacts");
    expect(html).toContain("0 of 1 loaded");
    expect(html).not.toContain("No artifacts yet");
    expect(html).not.toContain('aria-label="Selected artifact details"');
    expect(checkboxNodes(p, p.view)[0].props.disabled).toBe(true);
    const nodes = elements(ArtifactsPageContent(p));
    const clear = nodes.find((node) => node.type === Button && node.props.children === "Clear filters") as React.ReactElement<React.ComponentProps<typeof Button>>;
    click(clear);
    expect(p.onViewChange).toHaveBeenCalledExactlyOnceWith({ query: "", format: "all", source: "all", period: "all" });
  });

  it("emits partial view updates for search, filters, sort, grouping and detail inspection", () => {
    const p = contentProps();
    const nodes = elements(ArtifactsPageContent(p));
    const search = nodes.find((node) => node.type === SearchInput) as React.ReactElement<React.ComponentProps<typeof SearchInput>>;
    search.props.onChange?.({ target: { value: "Research" } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onViewChange).toHaveBeenLastCalledWith({ query: "Research" });
    for (const [label, value, change] of [
      ["Artifact format", "image", { format: "image" }], ["Creation source", "automation", { source: "automation" }],
      ["Creation date", "30", { period: "30" }], ["Sort artifacts", "oldest", { sort: "oldest" }],
    ] as const) {
      const control = nodes.find((node) => node.props.label === label) as React.ReactElement<{ onChange: (value: string) => void }>;
      expect(control).toBeDefined();
      control.props.onChange(value);
      expect(p.onViewChange).toHaveBeenLastCalledWith(change);
    }
    for (const [label, group] of [["By agent", "agent"], ["By automation", "automation"], ["All files", "none"]] as const) {
      const button = nodes.find((node) => node.type === Button && React.Children.toArray(node.props.children as React.ReactNode).includes(label)) as React.ReactElement<React.ComponentProps<typeof Button>>;
      click(button);
      expect(p.onViewChange).toHaveBeenLastCalledWith({ group });
    }
    click(nodes.find((node) => node.props["aria-label"] === "Show details: Weekly report") as React.ReactElement<React.ComponentProps<typeof Button>>);
    expect(p.onViewChange).toHaveBeenLastCalledWith({ activeId: artifact.artifact_id });
    expect(p.onSelectionChange).not.toHaveBeenCalled();
    expect(p.onDelete).not.toHaveBeenCalled();
  });

  it.each([{ locked: true }, { loading: true }])("guards all view callbacks while busy: %s", (busy) => {
    const p = contentProps(busy);
    const nodes = elements(ArtifactsPageContent(p));
    const search = nodes.find((node) => node.type === SearchInput) as React.ReactElement<React.ComponentProps<typeof SearchInput>>;
    expect(search.props.disabled).toBe(true);
    search.props.onChange?.({ target: { value: "changed" } } as React.ChangeEvent<HTMLInputElement>);
    for (const node of nodes.filter((node) => ["Artifact format", "Creation source", "Creation date", "Sort artifacts"].includes(node.props.label as string))) {
      expect(node.props.disabled).toBe(true);
      (node.props.onChange as (value: string) => void)("all");
    }
    for (const node of nodes.filter((node) => node.type === Button)) (node.props.onClick as () => void)?.();
    expect(p.onViewChange).not.toHaveBeenCalled();
  });

  it("discloses hidden selection and selects/clears only filtered IDs, while bulk delete retains the full selection", () => {
    const hidden = { ...artifact, artifact_id: "hidden", title: "Other file" };
    const p = contentProps({ artifacts: [artifact, hidden], selected: ["hidden"], view: view({ query: "Weekly" }) });
    expect(contentMarkup(p)).toContain("1 selected (1 hidden by filters)");
    expect(contentMarkup(p)).toContain("1 of 2 loaded");
    const top = checkboxNodes(p, p.view)[0];
    expect(top.props.checked).toBe(false);
    top.props.onChange?.({ currentTarget: { checked: true } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["hidden", "artifact-1"]);
    const both = { ...p, selected: ["hidden", "artifact-1"] };
    expect(checkboxNodes(both, both.view)[0].props.checked).toBe(true);
    checkboxNodes(both, both.view)[0].props.onChange?.({ currentTarget: { checked: false } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["hidden"]);
    checkboxNodes(both, both.view)[1].props.onChange?.({ currentTarget: { checked: false } } as React.ChangeEvent<HTMLInputElement>);
    expect(p.onSelectionChange).toHaveBeenLastCalledWith(["hidden"]);
    click(buttonNodes(p, p.view).find((button) => React.Children.toArray(button.props.children).includes("Delete selected")));
    expect(p.onBulkDelete).toHaveBeenCalledOnce();
    expect(p.selected).toEqual(["hidden"]);
    click(buttonNodes(p, p.view).find((button) => button.props.children === "Clear selection"));
    expect(p.onSelectionChange).toHaveBeenLastCalledWith([]);
  });

  it("uses the first sorted result by default, honors active IDs and falls back after deletion or filtering", () => {
    const newer = { ...artifact, artifact_id: "newer", title: "New image", artifact_type: "image" as const, created_at: "2026-10-02T12:00:00Z" };
    const p = contentProps({ artifacts: [artifact, newer] });
    expect(detailTitles(p)).toEqual(["Show details: New image", "Show details: Weekly report"]);
    expect(activeTitles(p)).toEqual(["Show details: New image"]);
    expect(contentMarkup(p)).toContain('aria-label="Details for New image"');
    expect(activeTitles({ ...p, artifacts: [artifact] })).toEqual(["Show details: Weekly report"]);
    const chosen = { ...p, view: view({ activeId: artifact.artifact_id }) };
    expect(activeTitles(chosen)).toEqual(["Show details: Weekly report"]);
    expect(contentMarkup(chosen)).toContain('aria-label="Details for Weekly report"');
    const deleted = { ...chosen, artifacts: [newer] };
    expect(activeTitles(deleted)).toEqual(["Show details: New image"]);
    expect(contentMarkup(deleted)).not.toContain('aria-label="Details for Weekly report"');
    const filtered = { ...chosen, view: view({ activeId: artifact.artifact_id, format: "image" }) };
    expect(activeTitles(filtered)).toEqual(["Show details: New image"]);
    expect(contentMarkup(filtered)).not.toContain('aria-label="Details for Weekly report"');
    expect(activeTitles({ ...p, view: view({ activeId: "stale-id", sort: "oldest" }) })).toEqual(["Show details: Weekly report"]);
    expect(contentMarkup({ ...chosen, artifacts: [] })).not.toContain('aria-label="Selected artifact details"');
    expect(p.onViewChange).not.toHaveBeenCalled();
  });
});
