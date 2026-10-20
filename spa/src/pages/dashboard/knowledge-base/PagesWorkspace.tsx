import { useEffect, useMemo, useState } from "react";
import { FileText, Globe } from "lucide-react";
import {
  AlertBanner,
  Button,
  InlineEmptyState,
  LoadingState,
  SearchInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../../components/ui";
import { useMediaQuery } from "../../../hooks/useMediaQuery";
import type { KnowledgePage, KnowledgePageState } from "../../../types/knowledge";
import { PageReader } from "./PageReader";
import { shortAddress } from "./knowledgePageDetail";
import { pageBadge, pageTabs } from "./knowledgePages";
import { countByState, filterPages, relativeAge, sectionsOf } from "./knowledgeWorkspace";
import styles from "./PagesWorkspace.module.css";

const ALL_SECTIONS = "all";

interface PagesWorkspaceProps {
  kbId: string;
  /** None until loaded. */
  pages: KnowledgePage[] | null;
  /** The knowledge base has more pages than were loaded. */
  truncated: boolean;
  error: string | null;
  /** Changes when a crawl ends, so the reader shows what the index holds now. */
  refreshKey: string;
  selectedUrl: string | null;
  /** The chunk a search found, outlined in the reader. */
  chunkId: string | null;
  section: string | null;
  onSelect: (url: string | null) => void;
  onSection: (section: string | null) => void;
  onAsk: (question: string) => void;
}

const DOT_CLASS: Record<KnowledgePageState, string> = {
  live: "dotLive",
  failing: "dotFailing",
  duplicate: "dotDuplicate",
  gone: "dotGone",
};

/** The pages as three panes: the sections, the pages in them, and the chosen page to read. A narrow screen shows
 *  one at a time. */
export function PagesWorkspace({
  kbId,
  pages,
  truncated,
  error,
  refreshKey,
  selectedUrl,
  chunkId,
  section,
  onSelect,
  onSection,
  onAsk,
}: PagesWorkspaceProps) {
  const [state, setState] = useState<KnowledgePageState | undefined>(undefined);
  const [search, setSearch] = useState("");
  const [focus, setFocus] = useState(false);
  const twoPanes = useMediaQuery("(min-width: 768px)");
  const threePanes = useMediaQuery("(min-width: 1360px)");

  const shown = useMemo(
    () => filterPages(pages ?? [], { state, section: section ?? undefined, search }),
    [pages, state, section, search]
  );
  const sections = useMemo(() => sectionsOf(pages ?? []), [pages]);
  const tabs = useMemo(() => pageTabs(countByState(pages ?? [])), [pages]);

  // With room for the reader beside the list, it shouldn't sit empty
  useEffect(() => {
    if (twoPanes && !selectedUrl && shown.length > 0) onSelect(shown[0].url);
  }, [twoPanes, selectedUrl, shown, onSelect]);

  // j and k move through the list, as in a mail client
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.closest("input, textarea, select, [contenteditable]") || event.metaKey || event.ctrlKey) return;
      if (event.key === "f" && threePanes) return setFocus((on) => !on);
      if (event.key !== "j" && event.key !== "k") return;
      const at = shown.findIndex((page) => page.url === selectedUrl);
      const next = shown[Math.min(shown.length - 1, Math.max(0, at + (event.key === "j" ? 1 : -1)))];
      if (next) onSelect(next.url);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shown, selectedUrl, threePanes, onSelect]);

  if (error && !pages) return <AlertBanner message={error} variant="error" />;
  if (!pages) return <LoadingState className={styles.loading} size="default" />;
  if (pages.length === 0) {
    return (
      <InlineEmptyState
        icon={Globe}
        title="No pages yet"
        description="Crawl a site or upload a file, and its pages appear here"
      />
    );
  }

  const reading = selectedUrl !== null;
  const focused = focus && threePanes;

  return (
    <div className={`${styles.work} ${reading ? styles.reading : styles.idle} ${focused ? styles.focus : ""}`}>
      <nav className={styles.tree} aria-label="Sections">
        <p className={styles.label}>Sections</p>
        <Button
          variant="ghost"
          className={styles.node}
          aria-pressed={!section}
          onClick={() => onSection(null)}
        >
          <span className={styles.nodeName}>Everything</span>
          <span className={styles.nodeCount}>{pages.length}</span>
        </Button>
        {sections.map((item) => (
          <Button
            key={item.id}
            variant="ghost"
            className={styles.node}
            aria-pressed={section === item.id}
            onClick={() => onSection(item.id)}
          >
            <span className={`${styles.dot} ${item.attention ? styles.dotFailing : styles.dotLive}`} aria-hidden="true" />
            <span className={styles.nodeName}>{item.id}</span>
            <span className={styles.nodeCount}>{item.count}</span>
          </Button>
        ))}
      </nav>

      <section className={styles.list} aria-label="Pages">
        <div className={styles.tools}>
          <SearchInput
            placeholder="Find a page by its address or title"
            aria-label="Find a page"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className={styles.sectionSelect}>
            <Select value={section ?? ALL_SECTIONS} onValueChange={(value) => onSection(value === ALL_SECTIONS ? null : value)}>
              <SelectTrigger aria-label="Section">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_SECTIONS}>Everything ({pages.length})</SelectItem>
                {sections.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.id} ({item.count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {tabs.length > 2 && (
            <div className={styles.chips}>
              {tabs.map((tab) => (
                <Button
                  key={tab.state ?? "all"}
                  size="sm"
                  variant={tab.state === state ? "secondary" : "ghost"}
                  aria-pressed={tab.state === state}
                  onClick={() => setState(tab.state)}
                >
                  {tab.label} {tab.count}
                </Button>
              ))}
            </div>
          )}
        </div>

        <div className={styles.rows}>
          {shown.length === 0 ? (
            <InlineEmptyState icon={Globe} title="No pages match" description="Try a different search, section or tab" />
          ) : (
            shown.map((page) => {
              const badge = pageBadge(page);
              return (
                <button
                  key={page.url}
                  type="button"
                  className={styles.row}
                  aria-current={page.url === selectedUrl ? "true" : undefined}
                  onClick={() => onSelect(page.url)}
                >
                  <span className={`${styles.dot} ${styles[DOT_CLASS[page.state]]}`} role="img" aria-label={badge.label} />
                  <span className={styles.rowTitle}>{page.title || shortAddress(page.url)}</span>
                  <span className={styles.rowMeta}>
                    {page.chunk_count} {page.chunk_count === 1 ? "chunk" : "chunks"}
                  </span>
                  <span className={styles.rowAddress}>
                    {page.source === "upload" && <FileText className={styles.rowIcon} aria-hidden="true" />}
                    {shortAddress(page.url)} • {page.state === "gone" ? "removed" : `read ${relativeAge(page.last_read_at)}`}
                  </span>
                </button>
              );
            })
          )}
        </div>

        <p className={styles.foot}>
          {shown.length} of {pages.length} pages{truncated && " (the first 1,000 are loaded)"}
          <span className={styles.keys}>
            {" "}
            • <kbd>j</kbd> <kbd>k</kbd> to move
          </span>
        </p>
      </section>

      <article className={styles.readerPane}>
        <PageReader
          kbId={kbId}
          url={selectedUrl}
          refreshKey={refreshKey}
          highlight={search.trim()}
          chunkId={chunkId}
          onOpenPage={onSelect}
          onAsk={onAsk}
          onBack={() => onSelect(null)}
          focus={threePanes ? { on: focused, toggle: () => setFocus((on) => !on) } : undefined}
        />
      </article>
    </div>
  );
}
