import type { StatusBadgeProps } from "../../../components/ui";
import type { KnowledgePage } from "../../../types/knowledge";

export interface PageBadge {
  status: StatusBadgeProps["status"];
  label: string;
}

/** How a page's state reads as a badge: what agents can find from it. */
export function pageBadge(page: KnowledgePage): PageBadge {
  if (page.needs_attention) return { status: "error", label: "Needs a look" };
  if (page.state === "failing") return { status: "warning", label: "Couldn't read" };
  if (page.state === "gone") return { status: "cancelled", label: "Removed" };
  return { status: "success", label: "Live" };
}

/** One line under the page's title: what it holds, or why it doesn't. */
export function pageSummary(page: KnowledgePage, formatDate: (iso: string | null) => string): string {
  const chunks = `${page.chunk_count} ${page.chunk_count === 1 ? "chunk" : "chunks"}`;
  if (page.state === "gone") return `Removed ${formatDate(page.last_read_at)}: ${page.reason}`;
  if (page.state === "failing") {
    const runs = page.consecutive_failures === 1 ? "the last crawl" : `the last ${page.consecutive_failures} crawls`;
    return `${page.reason} in ${runs}. Agents still use its last good read (${chunks}).`;
  }
  return page.last_read_at ? `${chunks} • read ${formatDate(page.last_read_at)}` : chunks;
}

/** Counts by what agents see, for the card's header. */
export function pageCounts(pages: KnowledgePage[]): { live: number; failing: number; gone: number } {
  return {
    live: pages.filter((page) => page.state === "live").length,
    failing: pages.filter((page) => page.state === "failing").length,
    gone: pages.filter((page) => page.state === "gone").length,
  };
}
