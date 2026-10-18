import { describe, expect, it } from "vitest";
import type { KnowledgePage } from "../../../types/knowledge";
import { pageBadge, pageSummary, pageTabs } from "./knowledgePages";

const page = (overrides: Partial<KnowledgePage> = {}): KnowledgePage => ({
  url: "https://example.com/pricing",
  title: "Pricing",
  description: "What it costs.",
  source: "https://example.com",
  state: "live",
  chunk_count: 12,
  last_read_at: "2026-10-18T09:00:00Z",
  consecutive_failures: 0,
  duplicate_of: "",
  needs_attention: false,
  reason: "",
  ...overrides,
});
const day = () => "Oct 18";

describe("a knowledge base page", () => {
  it("says a live page is live, with what it holds", () => {
    expect(pageBadge(page())).toEqual({ status: "success", label: "Live" });
    expect(pageSummary(page(), day)).toBe("12 chunks • read Oct 18");
  });

  it("says a failing page is still used from its last good read", () => {
    const failing = page({ state: "failing", consecutive_failures: 2, reason: "HTTP 503" });

    expect(pageBadge(failing).label).toBe("Couldn't read");
    expect(pageSummary(failing, day)).toBe("HTTP 503 in the last 2 crawls. Agents still use its last good read (12 chunks).");
  });

  it("asks for a look once a page has failed for long enough", () => {
    expect(pageBadge(page({ state: "failing", needs_attention: true }))).toEqual({ status: "error", label: "Needs a look" });
  });

  it("says why a removed page was removed", () => {
    const gone = page({ state: "gone", chunk_count: 0, reason: "HTTP 404" });

    expect(pageBadge(gone).label).toBe("Removed");
    expect(pageSummary(gone, day)).toBe("Removed Oct 18: HTTP 404");
  });

  it("says which page a duplicate stands behind", () => {
    const duplicate = page({ state: "duplicate", chunk_count: 0, duplicate_of: "https://example.com/contact" });

    expect(pageBadge(duplicate)).toEqual({ status: "info", label: "Duplicate" });
    expect(pageSummary(duplicate, day)).toBe("Says what https://example.com/contact says, so only that page is searched.");
  });

  it("offers a tab for each state that has pages, after one for all of them", () => {
    expect(pageTabs({ live: 40, failing: 0, gone: 2, duplicate: 3 })).toEqual([
      { state: undefined, label: "All", count: 45 },
      { state: "live", label: "Live", count: 40 },
      { state: "duplicate", label: "Duplicates", count: 3 },
      { state: "gone", label: "Removed", count: 2 },
    ]);
  });

  it("puts the pages that couldn't be read first, as the list does", () => {
    const [, first] = pageTabs({ live: 1, failing: 1, gone: 0, duplicate: 0 });

    expect(first).toEqual({ state: "failing", label: "Couldn't be read", count: 1 });
  });
});
