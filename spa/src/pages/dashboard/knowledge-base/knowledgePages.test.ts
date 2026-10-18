import { describe, expect, it } from "vitest";
import type { KnowledgePage } from "../../../types/knowledge";
import { pageBadge, pageCounts, pageSummary } from "./knowledgePages";

const page = (overrides: Partial<KnowledgePage> = {}): KnowledgePage => ({
  url: "https://example.com/pricing",
  title: "Pricing",
  source: "https://example.com",
  state: "live",
  chunk_count: 12,
  last_read_at: "2026-10-18T09:00:00Z",
  consecutive_failures: 0,
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

  it("counts pages by state", () => {
    expect(pageCounts([page(), page({ state: "gone" }), page({ state: "failing" }), page()])).toEqual({
      live: 2, failing: 1, gone: 1,
    });
  });
});
