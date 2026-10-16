import type { ToolActivity } from "../../types/message";

/** What Ila is doing, in her words, for each of her tools (api/src/builder/tools.py). */
type Phrase = (args: Record<string, unknown> | undefined) => string;

const MAX_QUERY_CHARS = 36;
const MAX_PAGES_NAMED = 2;

const TOOL_PHRASES: Record<string, Phrase> = {
  open_pages: (args) => {
    const pages = stringList(args, "page_ids").map(pageLabel);
    if (pages.length === 0) return "Reading up";
    const named = pages.slice(0, MAX_PAGES_NAMED).join(", ");
    return pages.length > MAX_PAGES_NAMED ? `Reading about ${named} and more` : `Reading about ${named}`;
  },
  search_book: (args) => {
    const query = stringArgument(args, "query");
    const prefix = stringArgument(args, "prefix");
    const where = prefix?.startsWith("account/") ? "your account" : "what I can build";
    if (query) return `Searching ${where} for “${truncate(query)}”`;
    return prefix ? `Looking through ${pageLabel(prefix)}` : "Searching";
  },
  show_form: () => "Preparing a few questions",
  plan_blueprint: () => "Planning your blueprint",
  apply_blueprint: () => "Building it",
  add_to_draft: (args) => {
    const page = stringArgument(args, "page_id");
    return page ? `Adding ${pageLabel(page)} to the draft` : "Adding it to the draft";
  },
  get_build_status: () => "Checking on your build",
};

/**
 * The line to show while a turn runs: the latest tool still running, in plain words; "Thinking" between tools; nothing
 * once the turn is over. Like the widget's "Using a tool…", it shows the current step and then goes.
 */
export function ilaStatus(activities: ToolActivity[], turnRunning: boolean): string | null {
  const running = [...activities].reverse().find((activity) => activity.status === "running");
  if (running) return (TOOL_PHRASES[running.tool_name]?.(running.tool_args) ?? "Working on it");
  return turnRunning ? "Thinking" : null;
}

/**
 * A book page id as a person would say it: `kind/Agent` → "agents", `skill/send_email` → "the Send Email skill",
 * `account/Agent/<id>/instructions` → "your agent's instructions". Ids are for Ila; people never see them.
 */
export function pageLabel(pageId: string): string {
  const [section, name, id, field] = pageId.split("/");
  if (section === "account") {
    if (field) return `your ${words(name)}'s ${humanize(field).toLowerCase()}`;
    if (id) return `your ${words(name)}`;
    return `your ${words(name)}s`;
  }
  if (section === "kind" && name) return `${words(name)}s`;
  if (section === "skill" && name) return `the ${humanize(name)} skill`;
  if (section === "recipe" && name) return `the ${humanize(name)} recipe`;
  if (section === "guide") return "how blueprints are written";
  return humanize(pageId);
}

function words(camelCase: string | undefined): string {
  return (camelCase ?? "").replace(/([a-z])([A-Z])/g, "$1 $2").toLowerCase();
}

function humanize(identifier: string): string {
  return identifier
    .split(/[._:\-/]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function stringArgument(args: Record<string, unknown> | undefined, key: string): string | null {
  const value = args?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringList(args: Record<string, unknown> | undefined, key: string): string[] {
  const value = args?.[key];
  const items = Array.isArray(value) ? value : typeof value === "string" ? [value] : [];
  return items.filter((item): item is string => typeof item === "string" && item.trim() !== "").map((item) => item.trim());
}

function truncate(value: string): string {
  return value.length > MAX_QUERY_CHARS ? `${value.slice(0, MAX_QUERY_CHARS)}…` : value;
}

/**
 * How long to keep the line on screen before the next one replaces it. Most of her tools finish in a moment, and a
 * line that flickers past is no better than none; so each stays long enough to read.
 */
export const MIN_SHOWN_MS = 800;

/** Milliseconds to wait before replacing a line shown since `shownSince`; 0 when it has been up long enough. */
export function holdDelay(shownSince: number, now: number, minShown = MIN_SHOWN_MS): number {
  return Math.max(0, minShown - (now - shownSince));
}
