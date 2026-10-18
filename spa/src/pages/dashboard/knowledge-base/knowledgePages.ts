import type { StatusBadgeProps } from "../../../components/ui";
import type { KnowledgePage, KnowledgePageCounts, KnowledgePageState } from "../../../types/knowledge";

export interface PageBadge {
  status: StatusBadgeProps["status"];
  label: string;
}

/** How a page's state reads as a badge: what agents can find from it. */
export function pageBadge(page: KnowledgePage): PageBadge {
  if (page.needs_attention) return { status: "error", label: "Needs a look" };
  if (page.state === "failing") return { status: "warning", label: "Couldn't read" };
  if (page.state === "gone") return { status: "cancelled", label: "Removed" };
  if (page.state === "duplicate") return { status: "info", label: "Duplicate" };
  return { status: "success", label: "Live" };
}

/** One line under the page's title: what it holds, or why it doesn't. */
export function pageSummary(page: KnowledgePage, formatDate: (iso: string | null) => string): string {
  const chunks = `${page.chunk_count} ${page.chunk_count === 1 ? "chunk" : "chunks"}`;
  if (page.state === "gone") return `Removed ${formatDate(page.last_read_at)}: ${page.reason}`;
  if (page.state === "duplicate") return `Says what ${page.duplicate_of} says, so only that page is searched.`;
  if (page.state === "failing") {
    const runs = page.consecutive_failures === 1 ? "the last crawl" : `the last ${page.consecutive_failures} crawls`;
    return `${page.reason} in ${runs}. Agents still use its last good read (${chunks}).`;
  }
  return page.last_read_at ? `${chunks} • read ${formatDate(page.last_read_at)}` : chunks;
}

export interface PageTab {
  /** The state it lists; undefined lists every page. */
  state: KnowledgePageState | undefined;
  label: string;
  count: number;
}

const TAB_LABELS: [KnowledgePageState, string][] = [
  ["failing", "Couldn't be read"],
  ["live", "Live"],
  ["duplicate", "Duplicates"],
  ["gone", "Removed"],
];

/** The page list's tabs: every page, then each state the knowledge base has pages in. */
export function pageTabs(counts: KnowledgePageCounts): PageTab[] {
  const all = TAB_LABELS.reduce((sum, [state]) => sum + counts[state], 0);
  return [
    { state: undefined, label: "All", count: all },
    ...TAB_LABELS.filter(([state]) => counts[state] > 0).map(([state, label]) => ({ state, label, count: counts[state] })),
  ];
}
