import { describe, expect, it } from "vitest";
import type { PageChunk } from "../../../types/knowledge";
import { chunkLevel, chunkTotals, shortAddress } from "./knowledgePageDetail";

const chunk = (overrides: Partial<PageChunk> = {}): PageChunk => ({
  chunk_id: "c1",
  level: 1,
  section_heading: "Plans",
  content: "Seats cost ten pounds.",
  word_count: 4,
  ...overrides,
});

describe("a page's chunks", () => {
  it("names the level a chunk was cut at", () => {
    expect([0, 1, 2].map((level) => chunkLevel(chunk({ level })))).toEqual(["Whole page", "Section", "Paragraph"]);
  });

  it("adds up what the page holds", () => {
    expect(chunkTotals([chunk({ word_count: 1000 }), chunk({ word_count: 234 })])).toBe("2 chunks • 1,234 words");
    expect(chunkTotals([chunk()])).toBe("1 chunk • 4 words");
  });

  it("shows an address without its scheme", () => {
    expect(shortAddress("https://innomight.com/about")).toBe("innomight.com/about");
  });
});
