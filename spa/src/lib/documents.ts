import type { StatusBadgeProps } from "../components/ui/status-badge";
import type { DocumentStatus, KnowledgeDocument } from "../types/knowledge";
import { ALLOWED_EXTENSIONS } from "../types/message";

/** How often to look again while a document is still being read. */
export const DOCUMENT_POLL_INTERVAL_MS = 3000;

/** What the chat's document picker offers. The server has the last word, and refuses what it can't read. */
export const CHAT_DOCUMENT_EXTENSIONS = [".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".html"];

function extensionOf(filename: string): string {
  const at = filename.lastIndexOf(".");
  return at >= 0 ? filename.slice(at).toLowerCase() : "";
}

/**
 * A dropped file only the documents path can take (a PDF, Word or slides): the text attachments read the rest
 * themselves, as they did before documents.
 */
export function readsOnlyAsDocument(filename: string): boolean {
  const extension = extensionOf(filename);
  return CHAT_DOCUMENT_EXTENSIONS.includes(extension) && !ALLOWED_EXTENSIONS.includes(extension);
}

const STATUS_VIEW: Record<DocumentStatus, { label: string; badge: StatusBadgeProps["status"] }> = {
  pending: { label: "Waiting to be read", badge: "in_progress" },
  parsing: { label: "Reading", badge: "in_progress" },
  indexing: { label: "Indexing", badge: "in_progress" },
  ready: { label: "Ready", badge: "completed" },
  failed: { label: "Failed", badge: "failed" },
  deleting: { label: "Deleting", badge: "cancelled" },
};

/** A pending document with an error was tried and will be again: it isn't merely waiting its first turn. */
export function documentStatusLabel(status: DocumentStatus, error = ""): string {
  return status === "pending" && error ? "Retrying" : STATUS_VIEW[status].label;
}

/** What went wrong, worth showing: why it failed, or why it is being tried again. Empty otherwise. */
export function documentProblem(document: KnowledgeDocument): string {
  if (!document.error) return "";
  if (document.status === "failed") return document.error;
  return document.status === "pending" ? `Will retry: ${document.error}` : "";
}

export function documentStatusBadge(status: DocumentStatus): StatusBadgeProps["status"] {
  return STATUS_VIEW[status].badge;
}

/**
 * Still being read or indexed, so worth asking about again. `deleting` is not: a delete finishes in its request, so a
 * document left `deleting` is one whose delete broke, and polling it would never end.
 */
export function isInFlight(status: DocumentStatus): boolean {
  return status === "pending" || status === "parsing" || status === "indexing";
}

export function anyInFlight(documents: KnowledgeDocument[]): boolean {
  return documents.some((document) => isInFlight(document.status));
}

/** The documents that were in flight in `before` and are ready in `after`: what changed the index. */
export function newlyReady(before: KnowledgeDocument[], after: KnowledgeDocument[]): KnowledgeDocument[] {
  const wasInFlight = new Set(before.filter((document) => isInFlight(document.status)).map((document) => document.document_id));
  return after.filter((document) => document.status === "ready" && wasInFlight.has(document.document_id));
}

/** What reading found, for a ready document: "12 pages • 3 tables". Empty when there's nothing to count. */
export function documentContents(document: KnowledgeDocument): string {
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
  return [
    document.page_count > 0 ? plural(document.page_count, "page") : null,
    document.table_count > 0 ? plural(document.table_count, "table") : null,
  ]
    .filter(Boolean)
    .join(" • ");
}
