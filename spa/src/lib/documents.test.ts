import { describe, expect, it } from "vitest";
import type { DocumentStatus, KnowledgeDocument } from "../types/knowledge";
import { anyInFlight, documentContents, documentProblem, documentStatusBadge, documentStatusLabel, isInFlight, newlyReady, readsOnlyAsDocument } from "./documents";

function document(id: string, status: DocumentStatus, counts: { pages?: number; tables?: number } = {}): KnowledgeDocument {
  return {
    document_id: id,
    owner_kind: "knowledge_base",
    owner_id: "kb-1",
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    size_bytes: 1024,
    metadata: "",
    source_url: "",
    status,
    parser: "",
    page_count: counts.pages ?? 0,
    table_count: counts.tables ?? 0,
    text_chars: 0,
    error: "",
    created_by: "user-1",
    created_at: "2026-10-24T10:00:00Z",
    updated_at: "2026-10-24T10:00:00Z",
  };
}

describe("document status", () => {
  it("treats pending, parsing and indexing as in flight, and nothing else", () => {
    expect(["pending", "parsing", "indexing"].every((status) => isInFlight(status as DocumentStatus))).toBe(true);
    expect(["ready", "failed", "deleting"].some((status) => isInFlight(status as DocumentStatus))).toBe(false);
  });

  it("shows every in-flight status as in progress, with its own label", () => {
    expect(documentStatusBadge("pending")).toBe("in_progress");
    expect(documentStatusBadge("indexing")).toBe("in_progress");
    expect(documentStatusBadge("ready")).toBe("completed");
    expect(documentStatusBadge("failed")).toBe("failed");
    expect(documentStatusLabel("parsing")).toBe("Reading");
  });
});

describe("polling", () => {
  it("keeps going while any document is in flight and stops when none are", () => {
    expect(anyInFlight([document("a", "ready"), document("b", "parsing")])).toBe(true);
    expect(anyInFlight([document("a", "ready"), document("b", "failed"), document("c", "deleting")])).toBe(false);
    expect(anyInFlight([])).toBe(false);
  });

  it("finds the documents that turned ready since the last look", () => {
    const before = [document("a", "indexing"), document("b", "ready"), document("c", "parsing")];
    const after = [document("a", "ready"), document("b", "ready"), document("c", "failed")];
    expect(newlyReady(before, after).map((doc) => doc.document_id)).toEqual(["a"]);
  });
});

describe("documentContents", () => {
  it("counts pages and tables, leaving out zeros", () => {
    expect(documentContents(document("a", "ready", { pages: 12, tables: 1 }))).toBe("12 pages • 1 table");
    expect(documentContents(document("a", "ready", { pages: 1 }))).toBe("1 page");
    expect(documentContents(document("a", "ready"))).toBe("");
  });
});

describe("readsOnlyAsDocument", () => {
  it("sends PDFs, Word and slides to documents and leaves what text attachments read to them", () => {
    expect(readsOnlyAsDocument("Report.PDF")).toBe(true);
    expect(readsOnlyAsDocument("notes.docx")).toBe(true);
    expect(readsOnlyAsDocument("deck.pptx")).toBe(true);
    expect(readsOnlyAsDocument("notes.md")).toBe(false);
    expect(readsOnlyAsDocument("sheet.xlsx")).toBe(false);
    expect(readsOnlyAsDocument("archive.zip")).toBe(false);
    expect(readsOnlyAsDocument("README")).toBe(false);
  });
});

describe("a document tried before", () => {
  const doc = (status: KnowledgeDocument["status"], error: string) => ({ status, error }) as KnowledgeDocument;

  it("is retrying, not waiting, when pending with an error", () => {
    expect(documentStatusLabel("pending", "ThrottlingException")).toBe("Retrying");
    expect(documentStatusLabel("pending")).toBe("Waiting to be read");
  });

  it("says why it is retried or failed, and nothing otherwise", () => {
    expect(documentProblem(doc("pending", "Throttled"))).toBe("Will retry: Throttled");
    expect(documentProblem(doc("failed", "Locked PDF"))).toBe("Locked PDF");
    expect(documentProblem(doc("ready", "old"))).toBe("");
  });
});
