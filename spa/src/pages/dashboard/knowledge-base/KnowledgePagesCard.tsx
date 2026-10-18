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
  SearchInput,
  SectionCardHeader,
  StatusBadge,
} from "../../../components/ui";
import { Inline, Stack } from "../../../components/layout";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePage, KnowledgePageCounts, KnowledgePageState } from "../../../types/knowledge";
import { pageBadge, pageSummary, pageTabs } from "./knowledgePages";
import styles from "./KnowledgePagesCard.module.css";

/** Pages loaded at a time: the list can be hundreds long. */
const PAGE_SIZE = 25;
const SEARCH_DELAY_MS = 300;

interface KnowledgePagesCardProps {
  kbId: string;
  /** Changes when a crawl ends, so the list reloads. */
  refreshKey: string;
  /** The page whose details are open beside the list. */
  selectedUrl: string | null;
  onSelect: (url: string) => void;
  formatDate: (iso: string | null) => string;
}

/** The knowledge base's pages as they are now: what agents can find, what couldn't be read, what was removed. */
export function KnowledgePagesCard({ kbId, refreshKey, selectedUrl, onSelect, formatDate }: KnowledgePagesCardProps) {
  const [counts, setCounts] = useState<KnowledgePageCounts | null>(null);
  const [state, setState] = useState<KnowledgePageState | undefined>(undefined);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [pages, setPages] = useState<KnowledgePage[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setSearch(typed.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [typed]);

  useEffect(() => {
    let current = true;
    knowledgeApiService
      .countPages(kbId)
      .then((loaded) => current && setCounts(loaded))
      .catch(() => undefined); // the list below says what went wrong
    return () => {
      current = false;
    };
  }, [kbId, refreshKey]);

  // The first page again whenever what's listed changes
  useEffect(() => {
    let current = true;
    setPages(null);
    knowledgeApiService
      .listPages(kbId, { state, search, limit: PAGE_SIZE })
      .then((loaded) => {
        if (!current) return;
        setPages(loaded.items);
        setCursor(loaded.next_cursor);
        setError(null);
      })
      .catch((err: unknown) => {
        if (current) setError(err instanceof Error ? err.message : "Couldn't load the pages");
      });
    return () => {
      current = false;
    };
  }, [kbId, refreshKey, state, search]);

  const showMore = async () => {
    setLoadingMore(true);
    try {
      const loaded = await knowledgeApiService.listPages(kbId, { state, search, limit: PAGE_SIZE, cursor });
      setPages((shown) => [...(shown ?? []), ...loaded.items]);
      setCursor(loaded.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load more pages");
    } finally {
      setLoadingMore(false);
    }
  };

  const tabs = counts ? pageTabs(counts) : [];
  const empty = counts !== null && tabs[0].count === 0;

  return (
    <Card>
      <CardHeader>
        <SectionCardHeader icon={Globe} title="Pages" />
      </CardHeader>
      <CardContent>
        <Stack gap="md">
          {error && <AlertBanner message={error} variant="error" />}
          {!empty && (
            <>
              {tabs.length > 2 && (
                <Inline gap="sm">
                  {tabs.map((tab) => (
                    <Button
                      key={tab.state ?? "all"}
                      size="sm"
                      variant={tab.state === state ? "secondary" : "ghost"}
                      onClick={() => setState(tab.state)}
                    >
                      {tab.label} {tab.count}
                    </Button>
                  ))}
                </Inline>
              )}
              <SearchInput
                placeholder="Find a page by its address or title"
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
              />
            </>
          )}
          {pages === null && !error ? (
            <LoadingState className={styles.loading} size="default" />
          ) : empty ? (
            <InlineEmptyState
              icon={Globe}
              title="No pages yet"
              description="Crawl a site or upload a file, and its pages appear here"
            />
          ) : pages?.length === 0 ? (
            <InlineEmptyState icon={Globe} title="No pages match" description="Try a different search or tab" />
          ) : (
            pages?.map((page) => {
              const badge = pageBadge(page);
              return (
                <button
                  key={page.url}
                  type="button"
                  className={page.url === selectedUrl ? styles.selectedRow : styles.row}
                  aria-pressed={page.url === selectedUrl}
                  onClick={() => onSelect(page.url)}
                >
                  <ListRow
                    icon={page.source === "upload" ? <FileText className={styles.rowIcon} /> : <Globe className={styles.rowIcon} />}
                    title={page.title || page.url}
                    subtitle={page.title ? page.url : undefined}
                    meta={pageSummary(page, formatDate)}
                    trailing={<StatusBadge status={badge.status} label={badge.label} />}
                  />
                </button>
              );
            })
          )}
          {cursor && (
            <Button variant="outline" size="sm" onClick={showMore} disabled={loadingMore}>
              {loadingMore ? "Loading..." : "Show more pages"}
            </Button>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
