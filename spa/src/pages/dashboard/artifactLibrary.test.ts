import { describe, expect, it } from "vitest";
import type { ArtifactResponse } from "../../services/artifacts";
import {
  INITIAL_ARTIFACT_LIBRARY_STATE, artifactFileBadge, artifactFormatLabel, artifactGroupIdentity, artifactOrigin, artifactOriginLabel, artifactSourceLabel,
  filterArtifacts, formatArtifactBytes, formatArtifactDate, groupArtifacts, selectVisibleArtifacts, shortArtifactId,
  type ArtifactLibraryState,
} from "./artifactLibrary";
import { EMPTY_ARTIFACT_SOURCE_NAMES, type ArtifactSourceNames } from "./artifactSources";

function artifact(overrides: Partial<ArtifactResponse> = {}): ArtifactResponse {
  return { artifact_id: "report", artifact_type: "html_report", title: "Weekly report", filename: "summary.html",
    mime_type: "text/html", size_bytes: 1024, created_at: "2026-10-19T12:00:00Z", source: { metadata: {} }, ...overrides };
}
function view(overrides: Partial<ArtifactLibraryState> = {}): ArtifactLibraryState {
  return { ...INITIAL_ARTIFACT_LIBRARY_STATE, ...overrides };
}
const names: ArtifactSourceNames = {
  agents: { analyst: "Research assistant" }, automations: { digest: "Morning digest" },
  conversations: { planning: "Quarterly planning" }, skills: { reports: "Report builder" },
};
const now = Date.parse("2026-10-20T12:00:00Z");
const automated = artifact({ source: { metadata: {}, agent_id: "analyst", automation_id: "digest", conversation_id: "planning",
  skill_id: "reports", automation_run_id: "run-123", automation_node_id: "node-456", message_id: "message-789" } });
const conversation = artifact({ artifact_id: "image", artifact_type: "image", title: "Chart", filename: "chart.png", mime_type: "image/png",
  created_at: "2026-10-13T12:00:00Z", source: { metadata: {}, agent_id: "analyst", conversation_id: "planning" } });
const legacy = artifact({ artifact_id: "legacy", artifact_type: "file", title: "Archive", filename: "archive.csv", mime_type: "text/csv", created_at: "2026-09-20T12:00:00Z" });
const fixtures = [legacy, conversation, automated];
function filtered(state: Partial<ArtifactLibraryState>, input: readonly ArtifactResponse[] = fixtures): string[] {
  return filterArtifacts(input, view(state), names, now).map((item) => item.artifact_id);
}

describe("artifact origin and source labels", () => {
  it("starts with an unfiltered newest-first agent view and no active artifact", () => {
    expect(INITIAL_ARTIFACT_LIBRARY_STATE).toEqual({ query: "", format: "all", source: "all", period: "all", sort: "newest", group: "agent", activeId: null, collapsedGroups: [] });
  });

  it.each([
    [{ automation_id: "automation", conversation_id: "chat" }, "automation"],
    [{ automation_run_id: "run", conversation_id: "chat" }, "automation"],
    [{ automation_node_id: "node" }, "automation"],
    [{ conversation_id: "chat" }, "conversation"],
    [{ agent_id: "agent", skill_id: "skill", message_id: "message" }, "unknown"],
    [{ automation_id: null, conversation_id: "" }, "unknown"],
    [{}, "unknown"],
  ] as const)("classifies source %j as %s", (source, expected) => {
    expect(artifactOrigin(artifact({ source: { metadata: {}, ...source } }))).toBe(expected);
  });

  it("uses resolved names and readable ID or missing fallbacks for every source kind", () => {
    for (const [kind, id, expected, prefix] of [
      ["agents", "analyst", "Research assistant", "Agent"], ["automations", "digest", "Morning digest", "Automation"],
      ["conversations", "planning", "Quarterly planning", "Conversation"], ["skills", "reports", "Report builder", "Skill"],
    ] as const) {
      expect(artifactSourceLabel(kind, id, names)).toBe(expected);
      expect(artifactSourceLabel(kind, "deleted", names)).toBe(`${prefix} · deleted`);
      for (const missing of [undefined, null, ""]) expect(artifactSourceLabel(kind, missing, names)).toBe(`${prefix} not recorded`);
    }
    expect(artifactOriginLabel(automated, names)).toBe("Morning digest");
    expect(artifactOriginLabel(conversation, names)).toBe("Quarterly planning");
    expect(artifactOriginLabel(legacy, names)).toBe("Source not recorded");
    expect(artifactOriginLabel(artifact({ source: { metadata: {}, automation_run_id: "orphan" } }), names)).toBe("Automation not recorded");
  });
});

const formatCases = [
  ["html_report", "HTML report"], ["image", "Image"], ["file", "File"], ["csv", "CSV"], ["markdown", "Markdown"],
  ["json", "JSON"], ["text", "Text"], ["code", "Code"], ["canvas", "Canvas"],
] as const;

describe("artifact formats", () => {
  const input = formatCases.map(([artifact_type]) => artifact({ artifact_id: artifact_type, artifact_type }));

  it.each(formatCases)("labels and filters %s as %s", (format, label) => {
    expect(artifactFormatLabel(format)).toBe(label);
    expect(filtered({ format }, input)).toEqual([format]);
  });

  it("retains all nine formats with no format filter and safely labels unknown runtime kinds", () => {
    expect(filtered({ format: "all" }, input)).toEqual(input.map((item) => item.artifact_id).sort());
    const unknown = artifact({ artifact_id: "future", artifact_type: "future_kind" as ArtifactResponse["artifact_type"] });
    expect(artifactFormatLabel(unknown.artifact_type)).toBe("File");
    expect(artifactFormatLabel("")).toBe("File");
    expect(filtered({ format: "all" }, [unknown])).toEqual(["future"]);
    for (const [format] of formatCases) expect(filtered({ format }, [unknown])).toEqual([]);
  });
});

describe("artifactFileBadge", () => {
  it.each([
    ["report.html", "HTML"], ["report.HTM", "HTML"], ["chart.PNG", "PNG"], ["photo.jpg", "JPG"],
    ["photo.JpEg", "JPG"], ["logo.svg", "SVG"], ["chart.webp", "WEBP"], ["animation.gif", "GIF"],
    ["data.csv", "CSV"], ["report.PDF", "PDF"], ["readme.md", "MD"], ["readme.markdown", "MD"],
    ["data.json", "JSON"], ["notes.txt", "TXT"], ["archive.tar.gz", "GZ"],
  ])("uses the actual extension of %s rather than the artifact kind or conflicting MIME", (filename, expected) => {
    expect(artifactFileBadge(artifact({ filename, mime_type: "application/octet-stream" }))).toBe(expected);
    if (filename !== "archive.tar.gz") expect(artifactFileBadge(artifact({ filename, mime_type: "text/plain" }))).toBe(expected);
  });

  it.each([
    ["TEXT/HTML; charset=UTF-8", "HTML"], ["image/png", "PNG"], [" IMAGE/JPEG ", "JPG"],
    ["image/svg+xml", "SVG"], ["image/webp", "WEBP"], ["image/tiff", "TIFF"], ["text/csv", "CSV"],
    ["application/pdf", "PDF"], ["text/markdown", "MD"], ["application/json", "JSON"], ["text/plain", "TXT"],
  ])("uses MIME %s for missing, unknown, or invalid extensions", (mime_type, expected) => {
    for (const filename of ["download", "", "download.xyz", "download.toolong", "download.bad-ext", ".env", "download."]) {
      expect(artifactFileBadge(artifact({ filename, mime_type }))).toBe(expected);
    }
  });

  it.each([
    ["result.xyz", "XYZ"], ["result.a1b2c", "A1B2C"], ["result.abcdef", "FILE"],
    ["result.bad-ext", "FILE"], ["result.é", "FILE"], ["result.<svg>", "FILE"],
    ["result.", "FILE"], [".env", "FILE"], ["README", "FILE"], ["", "FILE"],
    ["  folder/photo.JPEG  ", "JPG"], ["folder.csv/README", "FILE"], ["folder.csv\\README", "FILE"],
    ["result.constructor", "FILE"],
  ])("keeps unknown extensions short and safe: %s", (filename, expected) => {
    expect(artifactFileBadge(artifact({ filename, mime_type: "application/octet-stream", artifact_type: "file" }))).toBe(expected);
  });

  it.each([
    ["html_report", "HTML"], ["image", "IMG"], ["file", "FILE"], ["csv", "CSV"], ["markdown", "MD"],
    ["json", "JSON"], ["text", "TXT"], ["code", "CODE"], ["canvas", "CANVAS"],
  ] as const)("falls back to kind %s without inventing a file format", (artifact_type, expected) => {
    expect(artifactFileBadge(artifact({ filename: "", mime_type: "", artifact_type }))).toBe(expected);
  });

  it("handles unknown MIME and runtime kinds without assuming PNG or CSV", () => {
    expect(artifactFileBadge(artifact({ filename: "", mime_type: "image/unknown", artifact_type: "file" }))).toBe("IMG");
    expect(artifactFileBadge(artifact({ filename: "photo.xyz", mime_type: "image/unknown", artifact_type: "image" }))).toBe("XYZ");
    expect(artifactFileBadge(artifact({ filename: "", mime_type: "application/unknown", artifact_type: "future" as ArtifactResponse["artifact_type"] }))).toBe("FILE");
  });
});

describe("artifactGroupIdentity", () => {
  it.each([
    ["Research assistant", "RA"], ["  morning   digest extra  ", "MD"], ["Analyst", "AN"], ["a", "A"],
    ["Élodie Müller", "ÉM"], ["東京", "東京"], ["𐐨name", "𐐀N"], ["", "?"], ["   ", "?"],
  ])("takes initials from %j", (title, initials) => {
    expect(artifactGroupIdentity("agent:stable", title).initials).toBe(initials);
  });

  it("assigns deterministic tones by stable ID, independent of titles or call order", () => {
    const ids = ["agent:a", "agent:b", "agent:c", "automation:digest", "unknown", "", "agent:東京", "x".repeat(1000)];
    const identities = ids.map((id) => artifactGroupIdentity(id, "Original name"));
    for (const [index, id] of ids.entries()) {
      expect(artifactGroupIdentity(id, "Original name")).toEqual(identities[index]);
      expect(artifactGroupIdentity(id, "Renamed group").tone).toBe(identities[index].tone);
      expect(["blue", "purple", "green"]).toContain(identities[index].tone);
    }
    expect(new Set(identities.slice(0, 3).map(({ tone }) => tone)).size).toBe(3);
    for (const id of [...ids].reverse()) expect(artifactGroupIdentity(id, "Original name")).toEqual(identities[ids.indexOf(id)]);
  });
});

describe("filterArtifacts", () => {
  it.each([
    "Weekly REPORT", "summary.html", "report", "text/html", "analyst", "digest", "planning", "reports", "run-123", "node-456", "message-789",
    " Research ASSISTANT ", "Morning digest", "Report builder", "Quarterly planning",
  ])("searches artifact and source fields case-insensitively: %s", (query) => {
    expect(filtered({ query }, [automated])).toEqual(["report"]);
  });

  it("matches blank queries, handles absent metadata, and does not search serialized undefined or arbitrary metadata", () => {
    expect(filtered({ query: "   " })).toEqual(["report", "image", "legacy"]);
    expect(filtered({ query: "not present" })).toEqual([]);
    expect(filtered({ query: "undefined" })).toEqual([]);
    expect(filtered({ query: "null" })).toEqual([]);
    expect(filtered({ query: "private note" }, [artifact({ source: { metadata: { note: "private note" } } })])).toEqual([]);
    expect(filterArtifacts([legacy], view({ query: "Source not recorded" })).map((item) => item.artifact_id)).toEqual(["legacy"]);
  });

  it.each([
    [{ format: "html_report" }, ["report"]], [{ format: "image" }, ["image"]], [{ format: "file" }, ["legacy"]],
    [{ source: "automation" }, ["report"]], [{ source: "conversation" }, ["image"]], [{ source: "unknown" }, ["legacy"]],
    [{ period: "7" }, ["report", "image"]], [{ period: "30" }, ["report", "image", "legacy"]],
    [{ query: "Research", source: "automation", format: "html_report", period: "7", sort: "oldest" }, ["report"]],
    [{ query: "Quarterly", source: "conversation", format: "image", period: "7", sort: "name" }, ["image"]],
    [{ source: "automation", format: "image" }, []], [{ query: "Archive", period: "7" }, []],
  ] satisfies [Partial<ArtifactLibraryState>, string[]][])("combines filters with AND semantics: %j", (state, expected) => {
    expect(filtered(state)).toEqual(expected);
  });

  it.each(["7", "30"] as const)("includes the exact %s-day boundary and excludes earlier/invalid dates", (period) => {
    const cutoff = now - Number(period) * 86400000;
    const input = [artifact({ artifact_id: "boundary", created_at: new Date(cutoff).toISOString() }),
      artifact({ artifact_id: "too-old", created_at: new Date(cutoff - 1).toISOString() }),
      artifact({ artifact_id: "invalid", created_at: "not-a-date" })];
    expect(filtered({ period }, input)).toEqual(["boundary"]);
    expect(filtered({ period: "all" }, input)).toContain("invalid");
  });

  it("sorts empty titles by filename, prefers present titles, and breaks fallback ties by ID", () => {
    const input = Object.freeze([
      artifact({ artifact_id: "z", title: "", filename: "Alpha.csv" }),
      artifact({ artifact_id: "titled", title: "Bravo", filename: "Zulu.txt" }),
      artifact({ artifact_id: "a", title: "", filename: "Alpha.csv" }),
      artifact({ artifact_id: "last", title: "", filename: "Charlie.json" }),
    ]);
    expect(filtered({ sort: "name" }, input)).toEqual(["a", "z", "titled", "last"]);
    expect(input.map((item) => item.artifact_id)).toEqual(["z", "titled", "a", "last"]);
  });

  it("collapse state does not remove filtered members from selection or grouping", () => {
    const state = view({ collapsedGroups: ["agent:agent:analyst", "automation:automation:digest", "none:all"] });
    const visible = filterArtifacts(fixtures, state, names, now);
    expect(visible.map((item) => item.artifact_id)).toEqual(["report", "image", "legacy"]);
    expect(groupArtifacts(visible, "agent", names).flatMap((group) => group.artifacts)).toEqual(visible);
    expect(selectVisibleArtifacts(["hidden"], visible.map((item) => item.artifact_id), true)).toEqual(["hidden", "report", "image", "legacy"]);
  });

  it("sorts newest, oldest and name with deterministic ID ties without mutating the input", () => {
    const input = Object.freeze([
      artifact({ artifact_id: "b", title: "Alpha" }), artifact({ artifact_id: "a", title: "Alpha" }),
      artifact({ artifact_id: "c", title: "Zulu", created_at: "2026-10-01T12:00:00Z" }),
    ]);
    expect(filtered({ sort: "newest" }, input)).toEqual(["a", "b", "c"]);
    expect(filtered({ sort: "oldest" }, input)).toEqual(["c", "a", "b"]);
    expect(filtered({ sort: "name" }, input)).toEqual(["a", "b", "c"]);
    expect(input.map((item) => item.artifact_id)).toEqual(["b", "a", "c"]);
    expect(filterArtifacts(input, view(), names, now)[0]).toBe(input[1]);
    expect(filtered({}, [])).toEqual([]);
  });
});

describe("groupArtifacts", () => {
  it.each(["agent", "automation"] as const)("groups %s by stable IDs, never by equal display names, preserving result order", (group) => {
    const sourceKey = group === "agent" ? "agent_id" : "automation_id";
    const sameNames: ArtifactSourceNames = { ...EMPTY_ARTIFACT_SOURCE_NAMES,
      agents: { first: "Same name", second: "Same name" }, automations: { first: "Same name", second: "Same name" } };
    const first = artifact({ artifact_id: "a", source: { metadata: {}, [sourceKey]: "first" } });
    const second = artifact({ artifact_id: "b", source: { metadata: {}, [sourceKey]: "second" } });
    const third = { ...first, artifact_id: "c" };
    const input = Object.freeze([second, first, third]);
    const groups = groupArtifacts(input, group, sameNames);
    expect(groups.map(({ id, title, artifacts }) => ({ id, title, ids: artifacts.map((item) => item.artifact_id) }))).toEqual([
      { id: `${group}:second`, title: "Same name", ids: ["b"] }, { id: `${group}:first`, title: "Same name", ids: ["a", "c"] },
    ]);
    const renamed = groupArtifacts(input, group, EMPTY_ARTIFACT_SOURCE_NAMES);
    expect(renamed.map((item) => item.id)).toEqual(groups.map((item) => item.id));
    expect(renamed[0].title).not.toBe("Same name");
    expect(input).toEqual([second, first, third]);
  });

  it("groups automation runs together by automation ID and separates orphan runs, conversations and unknown sources", () => {
    const anotherRun = { ...automated, artifact_id: "second-run", source: { ...automated.source, automation_run_id: "other-run" } };
    const orphan = artifact({ artifact_id: "orphan", source: { metadata: {}, automation_run_id: "orphan-run" } });
    const otherOrphan = artifact({ artifact_id: "other-orphan", source: { metadata: {}, automation_run_id: "other-orphan-run" } });
    const groups = groupArtifacts([automated, anotherRun, orphan, otherOrphan, conversation, legacy], "automation", names);
    expect(groups.map(({ id, title, artifacts }) => ({ id, title, ids: artifacts.map((item) => item.artifact_id) }))).toEqual([
      { id: "automation:digest", title: "Morning digest", ids: ["report", "second-run"] },
      { id: "automation:orphan-run", title: "Automation not recorded", ids: ["orphan"] },
      { id: "automation:other-orphan-run", title: "Automation not recorded", ids: ["other-orphan"] },
      { id: "conversation", title: "Conversations", ids: ["image"] }, { id: "unknown", title: "Unknown source", ids: ["legacy"] },
    ]);
  });

  it("keeps a missing-agent bucket distinct from deleted agents and supports an ungrouped view", () => {
    const deleted = artifact({ artifact_id: "deleted", source: { metadata: {}, agent_id: "deleted" } });
    expect(groupArtifacts([legacy, deleted], "agent", names).map(({ id, title }) => ({ id, title }))).toEqual([
      { id: "agent:unknown", title: "Agent not recorded" }, { id: "agent:deleted", title: "Agent · deleted" },
    ]);
    expect(groupArtifacts(fixtures, "none", names)).toEqual([{ id: "all", title: "All files", description: "Every source, one view", artifacts: fixtures }]);
    for (const group of ["agent", "automation", "none"] as const) expect(groupArtifacts([], group, names)).toEqual([]);
  });
});

describe("selectVisibleArtifacts", () => {
  it("selects only filtered results, preserves hidden IDs, deduplicates and leaves inputs unchanged", () => {
    const selected = ["hidden", "report"];
    const visible = filtered({ source: "automation" });
    expect(selectVisibleArtifacts(selected, visible, true)).toEqual(["hidden", "report"]);
    expect(selectVisibleArtifacts(selected, visible, false)).toEqual(["hidden"]);
    expect(selectVisibleArtifacts(["hidden"], ["report", "report", "image"], true)).toEqual(["hidden", "report", "image"]);
    expect(selected).toEqual(["hidden", "report"]);
    expect(visible).toEqual(["report"]);
  });

  it("preserves selection for no matches and supports empty selection and single-row changes", () => {
    for (const checked of [true, false]) expect(selectVisibleArtifacts(["hidden"], [], checked)).toEqual(["hidden"]);
    expect(selectVisibleArtifacts([], ["report"], true)).toEqual(["report"]);
    expect(selectVisibleArtifacts(["hidden", "report"], ["report"], false)).toEqual(["hidden"]);
    expect(selectVisibleArtifacts([], ["report"], false)).toEqual([]);
  });
});

describe("artifact metadata formatting", () => {
  it.each([[0, "0 B"], [-1, "0 B"], [1, "1 B"], [1023, "1023 B"], [1024, "1.0 KB"], [10240, "10 KB"], [1048576, "1.0 MB"], [1073741824, "1.0 GB"]])("formats %s bytes as %s", (bytes, expected) => {
    expect(formatArtifactBytes(bytes as number)).toBe(expected);
  });

  it("shortens long IDs without altering short IDs and makes missing dates explicit", () => {
    expect(shortArtifactId("short-id")).toBe("short-id");
    expect(shortArtifactId("1234567890123456")).toBe("1234567890123456");
    expect(shortArtifactId("12345678901234567")).toBe("12345678…4567");
    expect(formatArtifactDate("invalid")).toBe("Date unavailable");
    expect(formatArtifactDate("")).toBe("Date unavailable");
    expect(formatArtifactDate(automated.created_at)).toBe(new Date(automated.created_at).toLocaleString(undefined, {
      day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    }));
  });
});
