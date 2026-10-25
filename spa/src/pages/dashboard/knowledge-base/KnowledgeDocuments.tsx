import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Loader2, RotateCcw, Trash2 } from "lucide-react";
import { AlertBanner, Button, ConfirmationDialog, InlineEmptyState, ListRow, LoadingState, StatusBadge } from "../../../components/ui";
import {
  DOCUMENT_POLL_INTERVAL_MS,
  anyInFlight,
  documentContents,
  documentProblem,
  documentStatusBadge,
  documentStatusLabel,
  isInFlight,
  newlyReady,
} from "../../../lib/documents";
import { knowledgeApiService } from "../../../services/knowledge";
import { HttpError } from "../../../services/http/client";
import type { KnowledgeDocument } from "../../../types/knowledge";
import { formatDate, formatFileSize } from "./knowledgeFormat";
import styles from "./KnowledgeRuns.module.css";

const PAGE_SIZE = 10;

interface KnowledgeDocumentsProps {
  kbId: string;
  /** Changes when files were uploaded: the list loads again from the newest. */
  refreshKey: number;
  /** A document finished indexing or was deleted, so the knowledge base's pages and totals changed. */
  onIndexChanged: () => void;
}

/**
 * The files uploaded to the knowledge base, newest first. While any is still being read it asks after those every
 * few seconds, and stops once none are.
 */
export function KnowledgeDocuments({ kbId, refreshKey, onIndexChanged }: KnowledgeDocumentsProps) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<KnowledgeDocument | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const documentsRef = useRef(documents);
  documentsRef.current = documents;

  const load = useCallback(
    async (options?: { cursor?: string | null; reset?: boolean }) => {
      setLoading(true);
      setError(null);
      try {
        const response = await knowledgeApiService.listDocuments(kbId, PAGE_SIZE, options?.cursor);
        setDocuments((previous) => (options?.reset ? response.items : [...previous, ...response.items]));
        setCursor(response.next_cursor);
        setHasMore(response.has_more);
      } catch (err) {
        console.error("Error loading documents:", err);
        setError("Failed to load documents.");
      } finally {
        setLoading(false);
      }
    },
    [kbId]
  );

  useEffect(() => {
    void load({ reset: true });
  }, [load, refreshKey]);

  // The interval restarts whenever the set of documents in flight changes, and isn't set when there are none
  const inFlightIds = documents.filter((document) => isInFlight(document.status)).map((document) => document.document_id);
  const inFlightKey = inFlightIds.join(",");
  useEffect(() => {
    if (!inFlightKey) return;
    const ids = inFlightKey.split(",");
    const timer = setInterval(async () => {
      const results = await Promise.allSettled(ids.map((id) => knowledgeApiService.getDocument(kbId, id)));
      const fresh = new Map<string, KnowledgeDocument>();
      const gone = new Set<string>();
      results.forEach((result, index) => {
        if (result.status === "fulfilled") fresh.set(result.value.document_id, result.value);
        else if (result.reason instanceof HttpError && result.reason.status === 404) gone.add(ids[index]);
      });
      if (newlyReady(documentsRef.current, [...fresh.values()]).length > 0) onIndexChanged();
      setDocuments((previous) =>
        previous.filter((document) => !gone.has(document.document_id)).map((document) => fresh.get(document.document_id) ?? document)
      );
    }, DOCUMENT_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [inFlightKey, kbId, onIndexChanged]);

  const retry = async (document: KnowledgeDocument) => {
    setRetrying(document.document_id);
    setError(null);
    try {
      const retried = await knowledgeApiService.retryDocument(kbId, document.document_id);
      setDocuments((previous) => previous.map((each) => (each.document_id === retried.document_id ? retried : each)));
    } catch (err) {
      console.error("Error retrying document:", err);
      setError(err instanceof Error ? err.message : "Couldn't retry the document.");
    } finally {
      setRetrying(null);
    }
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setError(null);
    try {
      await knowledgeApiService.deleteDocument(kbId, toDelete.document_id);
      setDocuments((previous) => previous.filter((document) => document.document_id !== toDelete.document_id));
      if (toDelete.status === "ready") onIndexChanged();
      setToDelete(null);
    } catch (err) {
      console.error("Error deleting document:", err);
      setError(err instanceof Error ? err.message : "Couldn't delete the document. Try again.");
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h2>
          Documents {anyInFlight(documents) && <Loader2 className={styles.spinner} aria-label="Reading documents" />}
        </h2>
      </div>
      {error && <AlertBanner message={error} variant="error" />}
      {loading && documents.length === 0 ? (
        <LoadingState className={styles.loading} size="default" />
      ) : documents.length === 0 ? (
        <InlineEmptyState icon={FileText} title="No documents yet" description="Upload a file to start building your knowledge base" />
      ) : (
        <div className={styles.uploads}>
          {documents.map((document) => {
            const contents = documentContents(document);
            const problem = documentProblem(document);
            return (
              <ListRow
                key={document.document_id}
                icon={<FileText className={styles.uploadIcon} />}
                title={document.filename}
                subtitle={[formatFileSize(document.size_bytes), contents, formatDate(document.created_at)].filter(Boolean).join(" • ")}
                meta={
                  problem ? (
                    <span className={styles.bad}>{problem}</span>
                  ) : (
                    document.metadata || undefined
                  )
                }
                trailing={
                  <div className={styles.headerSide}>
                    <StatusBadge
                      status={documentStatusBadge(document.status)}
                      label={documentStatusLabel(document.status, document.error)}
                      showIcon
                    />
                    {document.status === "failed" && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className={styles.retry}
                        aria-label={`Retry reading ${document.filename}`}
                        title="Retry"
                        disabled={retrying === document.document_id}
                        onClick={() => void retry(document)}
                      >
                        <RotateCcw className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className={styles.cancel}
                      aria-label={`Delete ${document.filename}`}
                      title="Delete"
                      onClick={() => setToDelete(document)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                }
              />
            );
          })}
        </div>
      )}
      {hasMore && (
        <Button size="sm" variant="outline" onClick={() => load({ cursor })} disabled={loading}>
          {loading ? "Loading..." : "Load more"}
        </Button>
      )}
      <ConfirmationDialog
        open={toDelete !== null}
        onOpenChange={(open) => !open && setToDelete(null)}
        title="Delete document"
        description={`Delete ${toDelete?.filename ?? "this document"}? What it added to the knowledge base is removed too.`}
        confirmText="Delete"
        variant="destructive"
        loading={deleting}
        loadingText="Deleting..."
        onConfirm={confirmDelete}
      />
    </section>
  );
}
