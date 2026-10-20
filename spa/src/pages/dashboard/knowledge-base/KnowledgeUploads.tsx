import { useCallback, useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { AlertBanner, Button, InlineEmptyState, ListRow, LoadingState } from "../../../components/ui";
import { knowledgeApiService } from "../../../services/knowledge";
import type { ContentUploadItem } from "../../../types/knowledge";
import { formatDate, formatFileSize } from "./knowledgeFormat";
import styles from "./KnowledgeRuns.module.css";

const PAGE_SIZE = 10;

/** The files uploaded to the knowledge base, oldest first, reloaded when `refreshKey` changes. */
export function KnowledgeUploads({ kbId, refreshKey }: { kbId: string; refreshKey: number }) {
  const [uploads, setUploads] = useState<ContentUploadItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (options?: { cursor?: string | null; reset?: boolean }) => {
      setLoading(true);
      setError(null);
      try {
        const response = await knowledgeApiService.listContentUploads(kbId, PAGE_SIZE, options?.cursor);
        setUploads((previous) =>
          [...(options?.reset ? response.items : [...previous, ...response.items])].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          )
        );
        setCursor(response.next_cursor);
        setHasMore(response.has_more);
      } catch (err) {
        console.error("Error loading uploads:", err);
        setError("Failed to load uploads.");
      } finally {
        setLoading(false);
      }
    },
    [kbId]
  );

  useEffect(() => {
    void load({ reset: true });
  }, [load, refreshKey]);

  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h2>Uploads</h2>
      </div>
      {error && <AlertBanner message={error} variant="error" />}
      {loading && uploads.length === 0 ? (
        <LoadingState className={styles.loading} size="default" />
      ) : uploads.length === 0 ? (
        <InlineEmptyState icon={FileText} title="No uploads yet" description="Upload a file to start building your knowledge base" />
      ) : (
        <div className={styles.uploads}>
          {uploads.map((upload) => (
            <ListRow
              key={upload.upload_id}
              icon={<FileText className={styles.uploadIcon} />}
              title={upload.filename}
              subtitle={`${formatFileSize(upload.size_bytes)} • ${formatDate(upload.created_at)}`}
              meta={upload.metadata || undefined}
              trailing={
                <>
                  <div>{upload.chunk_count} chunks</div>
                  <div>{upload.vector_count} vectors</div>
                </>
              }
            />
          ))}
        </div>
      )}
      {hasMore && (
        <Button size="sm" variant="outline" onClick={() => load({ cursor })} disabled={loading}>
          {loading ? "Loading..." : "Load more"}
        </Button>
      )}
    </section>
  );
}
