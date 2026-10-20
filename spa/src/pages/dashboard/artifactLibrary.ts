import type { ArtifactResponse, ArtifactType } from "../../services/artifacts";
import { EMPTY_ARTIFACT_SOURCE_NAMES, type ArtifactSourceNames } from "./artifactSources";

export type ArtifactOrigin = "automation" | "conversation" | "unknown";
export interface ArtifactLibraryState {
  query: string;
  format: "all" | ArtifactType;
  source: "all" | ArtifactOrigin;
  period: "all" | "7" | "30";
  sort: "newest" | "oldest" | "name";
  group: "agent" | "automation" | "none";
  activeId: string | null;
  collapsedGroups: string[];
}
export const INITIAL_ARTIFACT_LIBRARY_STATE: ArtifactLibraryState = {
  query: "", format: "all", source: "all", period: "all", sort: "newest", group: "agent", activeId: null, collapsedGroups: [],
};
export const ARTIFACT_FORMAT_LABELS: Record<ArtifactType, string> = {
  html_report: "HTML report", image: "Image", file: "File", csv: "CSV", markdown: "Markdown",
  json: "JSON", text: "Text", code: "Code", canvas: "Canvas",
};

export function artifactFormatLabel(type: string): string {
  return ARTIFACT_FORMAT_LABELS[type as ArtifactType] ?? "File";
}

const FILE_EXTENSION_BADGES = new Map(Object.entries({
  html: "HTML", htm: "HTML", png: "PNG", jpg: "JPG", jpeg: "JPG", svg: "SVG", gif: "GIF", webp: "WEBP",
  avif: "AVIF", bmp: "BMP", ico: "ICO", tif: "TIFF", tiff: "TIFF", csv: "CSV", pdf: "PDF",
  md: "MD", markdown: "MD", json: "JSON", txt: "TXT", xml: "XML", zip: "ZIP",
}));
const MIME_TYPE_BADGES = new Map(Object.entries({
  "text/html": "HTML", "application/xhtml+xml": "HTML", "image/png": "PNG", "image/jpeg": "JPG",
  "image/svg+xml": "SVG", "image/gif": "GIF", "image/webp": "WEBP", "image/avif": "AVIF",
  "image/bmp": "BMP", "image/x-icon": "ICO", "image/vnd.microsoft.icon": "ICO", "image/tiff": "TIFF",
  "text/csv": "CSV", "application/pdf": "PDF", "text/markdown": "MD", "text/x-markdown": "MD",
  "application/json": "JSON", "text/json": "JSON", "text/plain": "TXT", "application/xml": "XML",
  "text/xml": "XML", "application/zip": "ZIP",
}));
const ARTIFACT_KIND_BADGES = new Map(Object.entries({
  html_report: "HTML", image: "IMG", file: "FILE", csv: "CSV", markdown: "MD",
  json: "JSON", text: "TXT", code: "CODE", canvas: "CANVAS",
} satisfies Record<ArtifactType, string>));

export function artifactFileBadge(artifact: ArtifactResponse): string {
  const filename = artifact.filename.trim().split(/[\\/]/).pop() ?? "";
  const extension = /^.+\.([a-z0-9]+)$/i.exec(filename)?.[1].toLowerCase() ?? "";
  const knownExtension = FILE_EXTENSION_BADGES.get(extension);
  if (knownExtension) return knownExtension;
  const mime = artifact.mime_type.split(";")[0].trim().toLowerCase();
  const mimeBadge = MIME_TYPE_BADGES.get(mime);
  if (mimeBadge) return mimeBadge;
  if (/^[a-z0-9]{1,5}$/.test(extension)) return extension.toUpperCase();
  if (mime.startsWith("image/")) return "IMG";
  return ARTIFACT_KIND_BADGES.get(artifact.artifact_type) ?? "FILE";
}

export function artifactGroupIdentity(id: string, title: string): { initials: string; tone: "blue" | "purple" | "green" } {
  const words = title.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [...words[0]][0] + [...words[1]][0] : [...(words[0] ?? "")].slice(0, 2).join("");
  const initials = letters.toUpperCase() || "?";
  let hash = 0;
  for (const character of id) hash = (Math.imul(hash, 31) + character.codePointAt(0)!) >>> 0;
  const tones = ["blue", "purple", "green"] as const;
  return { initials, tone: tones[hash % tones.length] };
}

export function shortArtifactId(id: string): string {
  return id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

export function artifactOrigin(artifact: ArtifactResponse): ArtifactOrigin {
  if (artifact.source.automation_id || artifact.source.automation_run_id || artifact.source.automation_node_id) return "automation";
  return artifact.source.conversation_id ? "conversation" : "unknown";
}

export function artifactSourceLabel(kind: keyof ArtifactSourceNames, id: string | null | undefined, names: ArtifactSourceNames): string {
  const label = { agents: "Agent", automations: "Automation", conversations: "Conversation", skills: "Skill" }[kind];
  return id ? names[kind][id] || `${label} · ${shortArtifactId(id)}` : `${label} not recorded`;
}

export function artifactOriginLabel(artifact: ArtifactResponse, names: ArtifactSourceNames): string {
  switch (artifactOrigin(artifact)) {
    case "automation": return artifactSourceLabel("automations", artifact.source.automation_id, names);
    case "conversation": return artifactSourceLabel("conversations", artifact.source.conversation_id, names);
    default: return "Source not recorded";
  }
}

export function filterArtifacts(
  artifacts: readonly ArtifactResponse[], state: ArtifactLibraryState,
  names: ArtifactSourceNames = EMPTY_ARTIFACT_SOURCE_NAMES, now: number = Date.now(),
): ArtifactResponse[] {
  const query = state.query.trim().toLocaleLowerCase();
  const cutoff = state.period === "all" ? null : now - Number(state.period) * 86400000;
  return artifacts.filter((artifact) => {
    if (state.format !== "all" && artifact.artifact_type !== state.format) return false;
    if (state.source !== "all" && artifactOrigin(artifact) !== state.source) return false;
    if (cutoff !== null && !(Date.parse(artifact.created_at) >= cutoff)) return false;
    const source = artifact.source;
    return !query || [artifact.title, artifact.filename, artifact.artifact_id, artifact.mime_type,
      source.agent_id, source.automation_id, source.conversation_id, source.automation_run_id, source.automation_node_id, source.message_id, source.skill_id,
      artifactSourceLabel("agents", source.agent_id, names), artifactOriginLabel(artifact, names),
      artifactSourceLabel("skills", source.skill_id, names),
      source.conversation_id ? names.conversations[source.conversation_id] : "",
    ].join(" ").toLocaleLowerCase().includes(query);
  }).sort((a, b) => {
    if (state.sort === "name") return (a.title || a.filename).localeCompare(b.title || b.filename) || a.artifact_id.localeCompare(b.artifact_id);
    const difference = (Date.parse(a.created_at) || 0) - (Date.parse(b.created_at) || 0);
    return (state.sort === "oldest" ? difference : -difference) || a.artifact_id.localeCompare(b.artifact_id);
  });
}

export interface ArtifactGroup {
  id: string;
  title: string;
  description: string;
  artifacts: ArtifactResponse[];
}

export function groupArtifacts(artifacts: readonly ArtifactResponse[], group: ArtifactLibraryState["group"], names: ArtifactSourceNames): ArtifactGroup[] {
  const groups = new Map<string, ArtifactGroup>();
  for (const artifact of artifacts) {
    const source = artifact.source;
    const origin = artifactOrigin(artifact);
    let id: string;
    let title: string;
    let description: string;
    if (group === "agent") {
      id = source.agent_id ? `agent:${source.agent_id}` : "agent:unknown";
      title = artifactSourceLabel("agents", source.agent_id, names);
      description = source.agent_id ? "Files created by this agent" : "Creator metadata is unavailable";
    } else if (group === "automation") {
      id = origin === "automation" ? `automation:${source.automation_id || source.automation_run_id || "unknown"}` : origin;
      title = origin === "automation" ? artifactOriginLabel(artifact, names) : origin === "conversation" ? "Conversations" : "Unknown source";
      description = origin === "automation" ? "Automation output, across runs" : origin === "conversation" ? "Created directly in conversations" : "Source metadata is unavailable";
    } else {
      id = "all";
      title = "All files";
      description = "Every source, one view";
    }
    if (!groups.has(id)) groups.set(id, { id, title, description, artifacts: [] });
    groups.get(id)!.artifacts.push(artifact);
  }
  return [...groups.values()];
}

// Select/clear only the filtered set; explicit selections in other views stay selected.
export function selectVisibleArtifacts(selected: string[], visibleIds: string[], checked: boolean): string[] {
  const visible = new Set(visibleIds);
  return checked ? [...new Set([...selected, ...visibleIds])] : selected.filter((id) => !visible.has(id));
}

export function formatArtifactBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatArtifactDate(date: string): string {
  return Number.isNaN(Date.parse(date)) ? "Date unavailable" : new Date(date).toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}
