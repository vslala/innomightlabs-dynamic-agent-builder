import { useEffect, useState } from "react";
import { ExternalLink, FileText } from "lucide-react";
import {
  AlertBanner,
  Card,
  CardContent,
  CardHeader,
  InlineEmptyState,
  LoadingState,
  SectionCardHeader,
  StatusBadge,
} from "../../../components/ui";
import { Stack } from "../../../components/layout";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePageDetail } from "../../../types/knowledge";
import { chunkLevel, chunkTotals, shortAddress } from "./knowledgePageDetail";
import { pageBadge, pageSummary } from "./knowledgePages";
import styles from "./KnowledgePageDetailPanel.module.css";

interface KnowledgePageDetailPanelProps {
  kbId: string;
  /** The page chosen in the list; none shows a hint. */
  url: string | null;
  /** Changes when a crawl ends, so what's shown is what the index holds now. */
  refreshKey: string;
  formatDate: (iso: string | null) => string;
}

/** What the knowledge base holds of one page: what it says about itself, and each chunk as search returns it. */
export function KnowledgePageDetailPanel({ kbId, url, refreshKey, formatDate }: KnowledgePageDetailPanelProps) {
  const [shown, setShown] = useState<{ url: string; page: KnowledgePageDetail } | null>(null);
  const [error, setError] = useState<{ url: string; message: string } | null>(null);

  useEffect(() => {
    if (!url) return;
    let current = true;
    knowledgeApiService
      .getPage(kbId, url)
      .then((page) => {
        if (!current) return;
        setShown({ url, page });
        setError(null);
      })
      .catch((err: unknown) => {
        if (current) setError({ url, message: err instanceof Error ? err.message : "Couldn't load the page" });
      });
    return () => {
      current = false;
    };
  }, [kbId, url, refreshKey]);

  const page = shown && shown.url === url ? shown.page : null;
  const failed = error && error.url === url ? error.message : null;

  return (
    <Card>
      <CardHeader>
        <SectionCardHeader icon={FileText} title="Page details" />
      </CardHeader>
      <CardContent>
        {!url ? (
          <InlineEmptyState
            icon={FileText}
            title="Choose a page"
            description="Its chunks, and what agents can find from it, appear here"
          />
        ) : failed ? (
          <AlertBanner message={failed} variant="error" />
        ) : !page ? (
          <LoadingState className={styles.loading} size="default" />
        ) : (
          <Stack gap="md">
            <div>
              <div className={styles.titleRow}>
                <p className={styles.title}>{page.title || shortAddress(page.url)}</p>
                <StatusBadge status={pageBadge(page).status} label={pageBadge(page).label} />
              </div>
              {page.url.startsWith("http") ? (
                <a className={styles.address} href={page.url} target="_blank" rel="noreferrer">
                  {shortAddress(page.url)} <ExternalLink className={styles.linkIcon} aria-hidden="true" />
                </a>
              ) : (
                <p className={styles.address}>{page.url}</p>
              )}
              <p className={styles.summary}>{pageSummary(page, formatDate)}</p>
            </div>

            {page.description && <p className={styles.description}>{page.description}</p>}

            {page.duplicates.length > 0 && (
              <div>
                <p className={styles.label}>Also says the same</p>
                <ul className={styles.addresses}>
                  {page.duplicates.map((address) => (
                    <li key={address}>{shortAddress(address)}</li>
                  ))}
                </ul>
              </div>
            )}

            {page.chunks.length > 0 && (
              <div>
                <p className={styles.label}>{chunkTotals(page.chunks)}</p>
                <ol className={styles.chunks}>
                  {page.chunks.map((chunk) => (
                    <li key={chunk.chunk_id} className={styles.chunk}>
                      <p className={styles.chunkMeta}>
                        {chunkLevel(chunk)}
                        {chunk.section_heading && ` • ${chunk.section_heading}`} • {chunk.word_count} words
                      </p>
                      <p className={styles.chunkText}>{chunk.content}</p>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
