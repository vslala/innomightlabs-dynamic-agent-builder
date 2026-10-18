import { useEffect, useState } from "react";
import { Globe, FileText } from "lucide-react";
import {
  AlertBanner,
  Button,
  Card,
  CardContent,
  CardHeader,
  InlineEmptyState,
  ListRow,
  LoadingState,
  SectionCardHeader,
  StatusBadge,
} from "../../../components/ui";
import { Stack } from "../../../components/layout";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePage } from "../../../types/knowledge";
import { pageBadge, pageCounts, pageSummary } from "./knowledgePages";
import styles from "./KnowledgePagesCard.module.css";

/** Pages shown before "Show all": the list puts the ones that need a look first. */
const SHOWN_PAGES = 20;

interface KnowledgePagesCardProps {
  kbId: string;
  /** Changes when a crawl ends, so the list reloads. */
  refreshKey: string;
  formatDate: (iso: string | null) => string;
}

/** The knowledge base's pages as they are now: what agents can find, what couldn't be read, what was removed. */
export function KnowledgePagesCard({ kbId, refreshKey, formatDate }: KnowledgePagesCardProps) {
  const [pages, setPages] = useState<KnowledgePage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let current = true;
    knowledgeApiService
      .listPages(kbId)
      .then((loaded) => {
        if (!current) return;
        setPages(loaded);
        setError(null);
      })
      .catch((err: unknown) => {
        if (current) setError(err instanceof Error ? err.message : "Couldn't load the pages");
      });
    return () => {
      current = false;
    };
  }, [kbId, refreshKey]);

  const counts = pages ? pageCounts(pages) : null;
  const shown = pages && !showAll ? pages.slice(0, SHOWN_PAGES) : pages;

  return (
    <Card>
      <CardHeader>
        <SectionCardHeader
          icon={Globe}
          title="Pages"
          action={
            pages && pages.length > SHOWN_PAGES && (
              <Button size="sm" variant="outline" onClick={() => setShowAll((all) => !all)}>
                {showAll ? "Show fewer" : `Show all ${pages.length}`}
              </Button>
            )
          }
        />
      </CardHeader>
      <CardContent>
        <Stack gap="md">
          {error && <AlertBanner message={error} variant="error" />}
          {counts && pages && pages.length > 0 && (
            <p className={styles.counts}>
              {counts.live} live · {counts.failing} couldn't be read · {counts.gone} removed
            </p>
          )}
          {pages === null && !error ? (
            <LoadingState className={styles.loading} size="default" />
          ) : pages?.length === 0 ? (
            <InlineEmptyState
              icon={Globe}
              title="No pages yet"
              description="Crawl a site or upload a file, and its pages appear here"
            />
          ) : (
            shown?.map((page) => {
              const badge = pageBadge(page);
              return (
                <ListRow
                  key={page.url}
                  icon={page.source === "upload" ? <FileText className={styles.rowIcon} /> : <Globe className={styles.rowIcon} />}
                  title={page.title || page.url}
                  subtitle={page.title ? page.url : undefined}
                  meta={pageSummary(page, formatDate)}
                  trailing={<StatusBadge status={badge.status} label={badge.label} />}
                />
              );
            })
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
