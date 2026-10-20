import { describe, expect, it } from "vitest";
import type { KnowledgePage, SearchResult } from "../../../types/knowledge";
import {
  askVerdict,
  attentionItems,
  countByState,
  filterPages,
  freshness,
  healthPercent,
  pageAsMarkdown,
  pageSizes,
  relativeAge,
  sectionOf,
  sectionsOf,
} from "./knowledgeWorkspace";

const NOW = new Date("2026-10-20T12:00:00Z");
const daysAgo = (days: number) => new Date(NOW.getTime() - days * 86_400_000).toISOString();

function page(overrides: Partial<KnowledgePage>): KnowledgePage {
  return {
    url: "https://example.com/docs/a",
    title: "A",
    description: "",
    source: "https://example.com",
    state: "live",
    duplicate_of: "",
    chunk_count: 4,
    last_read_at: daysAgo(1),
    consecutive_failures: 0,
    needs_attention: false,
    reason: "",
    ...overrides,
  };
}

describe("sections", () => {
  it("is the first path segment, the root, or uploads", () => {
    expect(sectionOf(page({ url: "https://example.com/docs/a/b" }))).toBe("/docs");
    expect(sectionOf(page({ url: "https://example.com/" }))).toBe("/");
    expect(sectionOf(page({ url: "upload:notes.md", source: "upload" }))).toBe("Uploads");
  });

  it("lists the biggest first and flags those with a failing page", () => {
    const pages = [
      page({ url: "https://example.com/pricing" }),
      page({ url: "https://example.com/docs/a" }),
      page({ url: "https://example.com/docs/b", state: "failing" }),
    ];
    expect(sectionsOf(pages)).toEqual([
      { id: "/docs", count: 2, attention: true },
      { id: "/pricing", count: 1, attention: false },
    ]);
  });
});

describe("filterPages", () => {
  const pages = [
    page({ url: "https://example.com/docs/a", title: "Agents" }),
    page({ url: "https://example.com/pricing", title: "Plans", state: "failing" }),
  ];

  it("narrows by state, section and text together", () => {
    expect(filterPages(pages, { state: "failing" }).map((p) => p.title)).toEqual(["Plans"]);
    expect(filterPages(pages, { section: "/docs" }).map((p) => p.title)).toEqual(["Agents"]);
    expect(filterPages(pages, { search: " AGENTS " }).map((p) => p.title)).toEqual(["Agents"]);
    expect(filterPages(pages, { section: "/docs", state: "failing" })).toEqual([]);
  });
});

describe("health", () => {
  it("is the share of live pages, and nothing without pages", () => {
    expect(healthPercent(countByState([page({}), page({}), page({}), page({ state: "failing" })]))).toBe(75);
    expect(healthPercent(countByState([]))).toBeNull();
  });
});

describe("freshness", () => {
  it("buckets pages by how long ago they were read, leaving out removed and unread ones", () => {
    const buckets = freshness(
      [
        page({ last_read_at: daysAgo(2) }),
        page({ last_read_at: daysAgo(10) }),
        page({ last_read_at: daysAgo(45) }),
        page({ last_read_at: daysAgo(200) }),
        page({ last_read_at: daysAgo(3), state: "gone" }),
        page({ last_read_at: null }),
      ],
      NOW
    );
    expect(buckets.map((bucket) => bucket.count)).toEqual([1, 1, 1, 1]);
    expect(buckets.map((bucket) => bucket.old)).toEqual([false, false, true, true]);
  });
});

describe("relativeAge", () => {
  it("reads as days, then months", () => {
    expect(relativeAge(daysAgo(0), NOW)).toBe("today");
    expect(relativeAge(daysAgo(1), NOW)).toBe("1 day ago");
    expect(relativeAge(daysAgo(9), NOW)).toBe("9 days ago");
    expect(relativeAge(daysAgo(65), NOW)).toBe("2 mo ago");
    expect(relativeAge(null, NOW)).toBe("never");
  });
});

describe("pageSizes", () => {
  it("counts thin and large pages among those agents can search", () => {
    const sizes = pageSizes([
      page({ chunk_count: 1 }),
      page({ chunk_count: 3 }),
      page({ chunk_count: 26 }),
      page({ chunk_count: 0, state: "gone" }),
    ]);
    expect(sizes).toEqual({ average: 10, thin: 1, large: 1 });
  });
});

describe("attentionItems", () => {
  it("names failing pages, groups repeats under the page they repeat, and flags quiet pages", () => {
    const items = attentionItems(
      [
        page({ url: "https://example.com/a", title: "Security" }),
        page({ url: "https://example.com/b", title: "Keys", state: "duplicate", duplicate_of: "https://example.com/a" }),
        page({ url: "https://example.com/c", title: "Changelog", state: "failing", reason: "HTTP 503", consecutive_failures: 3 }),
        page({ url: "https://example.com/d", title: "About", last_read_at: daysAgo(40) }),
      ],
      NOW
    );
    expect(items.map((item) => item.kind)).toEqual(["failing", "duplicate", "stale"]);
    expect(items[0].detail).toBe("HTTP 503 in the last 3 crawls. Agents still use its last good read.");
    expect(items[1]).toMatchObject({ title: "A page repeats Security", urls: ["https://example.com/b"] });
    expect(items[2]).toMatchObject({ title: "1 page not read in over a month", urls: ["https://example.com/d"] });
  });

  it("has nothing to say about a healthy knowledge base", () => {
    expect(attentionItems([page({})], NOW)).toEqual([]);
  });
});

describe("askVerdict", () => {
  const result = (score: number): SearchResult => ({ chunk_id: "c", content: "", source_url: "", page_title: "", score });

  it("says whether the best chunk would let an agent answer", () => {
    expect(askVerdict([result(0.3), result(0.72)])).toBe("good");
    expect(askVerdict([result(0.45)])).toBe("weak");
    expect(askVerdict([result(0.1)])).toBe("none");
    expect(askVerdict([])).toBe("none");
  });
});

describe("pageAsMarkdown", () => {
  it("puts each chunk under its heading", () => {
    const text = pageAsMarkdown("Pricing", "https://example.com/pricing", [
      { section_heading: "Starter", content: "Free." },
      { section_heading: "", content: "Loose text." },
    ]);
    expect(text).toBe("# Pricing\n\nhttps://example.com/pricing\n\n## Starter\n\nFree.\n\nLoose text.\n");
  });
});
