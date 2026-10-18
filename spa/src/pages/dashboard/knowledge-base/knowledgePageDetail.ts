import type { PageChunk } from "../../../types/knowledge";

const LEVELS: Record<number, string> = { 0: "Whole page", 1: "Section", 2: "Paragraph" };

export function chunkLevel(chunk: PageChunk): string {
  return LEVELS[chunk.level] ?? "Chunk";
}

/** The page's address without the scheme, which is what tells pages of one site apart. */
export function shortAddress(url: string): string {
  return url.replace(/^https?:\/\//, "");
}

/** What the chunks add up to, for the line under the panel's title. */
export function chunkTotals(chunks: PageChunk[]): string {
  const words = chunks.reduce((sum, chunk) => sum + chunk.word_count, 0);
  return `${chunks.length} ${chunks.length === 1 ? "chunk" : "chunks"} • ${words.toLocaleString("en")} words`;
}
