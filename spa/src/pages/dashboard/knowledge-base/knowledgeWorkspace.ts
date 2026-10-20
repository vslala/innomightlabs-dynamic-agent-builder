import type { KnowledgePage, KnowledgePageCounts, KnowledgePageState, SearchResult } from "../../../types/knowledge";

const DAY_MS = 24 * 60 * 60 * 1000;
const STALE_AFTER_DAYS = 30;
/** A page this long or longer is split into many chunks, which search ranks less sharply. */
const LARGE_PAGE_CHUNKS = 20;

export const UPLOADS_SECTION = "Uploads";

/** The part of the site a page belongs to: its first path segment ("/docs"), the root ("/"), or "Uploads". */
export function sectionOf(page: KnowledgePage): string {
  if (page.source === "upload") return UPLOADS_SECTION;
  try {
    const segment = new URL(page.url).pathname.split("/")[1];
    return segment ? `/${segment}` : "/";
  } catch {
    return "/";
  }
}

export interface Section {
  id: string;
  count: number;
  /** One of its pages couldn't be read. */
  attention: boolean;
}

/** The sections the pages fall in, the biggest first. */
export function sectionsOf(pages: KnowledgePage[]): Section[] {
  const found = new Map<string, Section>();
  for (const page of pages) {
    const id = sectionOf(page);
    const section = found.get(id) ?? { id, count: 0, attention: false };
    section.count += 1;
    section.attention ||= page.state === "failing";
    found.set(id, section);
  }
  return [...found.values()].sort((a, b) => b.count - a.count || a.id.localeCompare(b.id));
}

export interface PageFilter {
  state?: KnowledgePageState;
  section?: string;
  search?: string;
}

export function filterPages(pages: KnowledgePage[], filter: PageFilter): KnowledgePage[] {
  const search = filter.search?.trim().toLowerCase();
  return pages.filter(
    (page) =>
      (!filter.state || page.state === filter.state) &&
      (!filter.section || sectionOf(page) === filter.section) &&
      (!search || `${page.title} ${page.url} ${page.description}`.toLowerCase().includes(search))
  );
}

export function countByState(pages: KnowledgePage[]): KnowledgePageCounts {
  const counts: KnowledgePageCounts = { live: 0, failing: 0, gone: 0, duplicate: 0 };
  for (const page of pages) counts[page.state] += 1;
  return counts;
}

/** The share of pages agents can use as they are, 0-100; none when there are no pages. */
export function healthPercent(counts: KnowledgePageCounts): number | null {
  const total = counts.live + counts.failing + counts.gone + counts.duplicate;
  return total === 0 ? null : Math.round((100 * counts.live) / total);
}

function ageInDays(iso: string, now: Date): number {
  return Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / DAY_MS));
}

/** "today", "3 days ago", "2 mo ago". */
export function relativeAge(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "never";
  const days = ageInDays(iso, now);
  if (days < 1) return "today";
  if (days < 30) return `${days} ${days === 1 ? "day" : "days"} ago`;
  return `${Math.round(days / 30)} mo ago`;
}

const FRESHNESS_BUCKETS = [
  { label: "Under a week", below: 7 },
  { label: "1-4 weeks", below: 30 },
  { label: "1-3 months", below: 90 },
  { label: "Over 3 months", below: Infinity },
];

export interface FreshnessBucket {
  label: string;
  count: number;
  /** Old enough that the site may have moved on. */
  old: boolean;
}

/** How long ago the pages agents use were last read. */
export function freshness(pages: KnowledgePage[], now: Date = new Date()): FreshnessBucket[] {
  const buckets = FRESHNESS_BUCKETS.map(({ label }, index) => ({ label, count: 0, old: index >= 2 }));
  for (const page of pages) {
    if (!page.last_read_at || page.state === "gone") continue;
    const days = ageInDays(page.last_read_at, now);
    buckets[FRESHNESS_BUCKETS.findIndex(({ below }) => days < below)].count += 1;
  }
  return buckets;
}

export interface PageSizes {
  /** Chunks per page that agents can search. */
  average: number;
  /** Pages of a single chunk. */
  thin: number;
  large: number;
}

export function pageSizes(pages: KnowledgePage[]): PageSizes {
  const searched = pages.filter((page) => page.state === "live" || page.state === "failing");
  const chunks = searched.reduce((sum, page) => sum + page.chunk_count, 0);
  return {
    average: searched.length ? Math.round((10 * chunks) / searched.length) / 10 : 0,
    thin: searched.filter((page) => page.chunk_count <= 1).length,
    large: searched.filter((page) => page.chunk_count >= LARGE_PAGE_CHUNKS).length,
  };
}

export interface Attention {
  kind: "failing" | "duplicate" | "stale";
  title: string;
  detail: string;
  /** The pages it is about, to open. */
  urls: string[];
}

/** What the owner can fix, the most pressing first: pages that can't be read, repeats, pages gone quiet. */
export function attentionItems(pages: KnowledgePage[], now: Date = new Date()): Attention[] {
  const items: Attention[] = [];
  for (const page of pages.filter((p) => p.state === "failing")) {
    const runs = page.consecutive_failures === 1 ? "the last crawl" : `the last ${page.consecutive_failures} crawls`;
    items.push({
      kind: "failing",
      title: page.title || page.url,
      detail: `${page.reason} in ${runs}. Agents still use its last good read.`,
      urls: [page.url],
    });
  }

  const repeats = new Map<string, string[]>();
  for (const page of pages.filter((p) => p.state === "duplicate")) {
    repeats.set(page.duplicate_of, [...(repeats.get(page.duplicate_of) ?? []), page.url]);
  }
  for (const [original, urls] of repeats) {
    const title = pages.find((page) => page.url === original)?.title || original;
    items.push({
      kind: "duplicate",
      title: urls.length === 1 ? `A page repeats ${title}` : `${urls.length} pages repeat ${title}`,
      detail: "Only the original is searched, so agents don't quote the same thing twice.",
      urls,
    });
  }

  const stale = pages.filter(
    (page) => page.state === "live" && page.last_read_at && ageInDays(page.last_read_at, now) >= STALE_AFTER_DAYS
  );
  if (stale.length > 0) {
    items.push({
      kind: "stale",
      title: `${stale.length} ${stale.length === 1 ? "page" : "pages"} not read in over a month`,
      detail: "The site may not link to them any more, or the crawl doesn't reach them.",
      urls: stale.map((page) => page.url),
    });
  }
  return items;
}

/** Scores from the index are cosine similarities: above `GOOD_SCORE` a chunk answers the question. */
export const GOOD_SCORE = 0.6;
export const WEAK_SCORE = 0.4;

export type AskVerdict = "good" | "weak" | "none";

/** Whether what came back would let an agent answer. */
export function askVerdict(results: SearchResult[]): AskVerdict {
  const best = Math.max(0, ...results.map((result) => result.score));
  if (best >= GOOD_SCORE) return "good";
  return best >= WEAK_SCORE ? "weak" : "none";
}

/** A page's chunks as Markdown, to paste elsewhere. */
export function pageAsMarkdown(title: string, url: string, chunks: { section_heading: string; content: string }[]): string {
  const body = chunks
    .map((chunk) => (chunk.section_heading ? `## ${chunk.section_heading}\n\n${chunk.content}` : chunk.content))
    .join("\n\n");
  return `# ${title}\n\n${url}\n\n${body}\n`;
}
