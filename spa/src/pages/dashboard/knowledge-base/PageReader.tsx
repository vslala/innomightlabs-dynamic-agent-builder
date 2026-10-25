import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Copy, ExternalLink, FileText, Maximize2, MessageCircleQuestion, Minimize2 } from "lucide-react";
import { AlertBanner, Button, InlineEmptyState, LoadingState, MarkdownRenderer, StatusBadge } from "../../../components/ui";
import { knowledgeApiService } from "../../../services/knowledge";
import type { KnowledgePageDetail, PageChunk } from "../../../types/knowledge";
import { chunkLevel, shortAddress } from "./knowledgePageDetail";
import { pageBadge } from "./knowledgePages";
import { pageAsMarkdown, relativeAge } from "./knowledgeWorkspace";
import styles from "./PageReader.module.css";

type View = "chunks" | "read";

interface PageReaderProps {
  kbId: string;
  /** The page chosen in the list; none shows a hint. */
  url: string | null;
  /** Changes when a crawl ends, so what's shown is what the index holds now. */
  refreshKey: string;
  /** A phrase to mark wherever the page says it. */
  highlight: string;
  /** The chunk a search found, scrolled to and outlined. */
  chunkId: string | null;
  onOpenPage: (url: string) => void;
  /** Ask the knowledge base about a chunk; the Ask tab runs it. */
  onAsk: (question: string) => void;
  /** Narrow screens show the reader alone, so it brings its own way back to the list. */
  onBack: () => void;
  /** On a wide screen the reader can take the whole width; none where it already does. */
  focus?: { on: boolean; toggle: () => void };
}

const LEVEL_CLASS = ["levelPage", "levelSection", "levelParagraph"];
const MAP_CLASS = ["mapPage", "mapSection", "mapParagraph"];

function Marked({ text, phrase }: { text: string; phrase: string }) {
  if (!phrase) return <>{text}</>;
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return (
    <>
      {text.split(new RegExp(`(${escaped})`, "ig")).map((part, index) =>
        part.toLowerCase() === phrase.toLowerCase() ? <mark key={index}>{part}</mark> : part
      )}
    </>
  );
}

/** What the knowledge base holds of one page: what it says about itself, and each chunk as search returns it. */
export function PageReader({ kbId, url, refreshKey, highlight, chunkId, onOpenPage, onAsk, onBack, focus }: PageReaderProps) {
  const [shown, setShown] = useState<{ url: string; page: KnowledgePageDetail } | null>(null);
  const [error, setError] = useState<{ url: string; message: string } | null>(null);
  const [view, setView] = useState<View>("chunks");
  const [jumpedTo, setJumpedTo] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const chunkRefs = useRef(new Map<string, HTMLLIElement>());

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
  const hot = jumpedTo ?? chunkId;

  useEffect(() => {
    if (page && chunkId) chunkRefs.current.get(chunkId)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [page, chunkId]);

  const jump = (chunk: PageChunk) => {
    setView("chunks");
    setJumpedTo(chunk.chunk_id);
    // The chunk list mounts first when coming from the reading view
    requestAnimationFrame(() => chunkRefs.current.get(chunk.chunk_id)?.scrollIntoView({ block: "center", behavior: "smooth" }));
  };

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied((now) => (now === key ? null : now)), 1500);
    } catch {
      setCopied(null);
    }
  };

  const back = (
    <Button variant="ghost" size="sm" className={styles.back} onClick={onBack}>
      <ArrowLeft className="h-4 w-4" />
      All pages
    </Button>
  );

  if (!url) {
    return (
      <div className={styles.reader}>
        <InlineEmptyState icon={FileText} title="Choose a page" description="Its chunks, and what agents can find from it, appear here" />
      </div>
    );
  }
  if (failed) {
    return (
      <div className={styles.reader}>
        <div className={styles.pad}>
          {back}
          <AlertBanner message={failed} variant="error" />
        </div>
      </div>
    );
  }
  if (!page) {
    return (
      <div className={styles.reader}>
        <div className={styles.pad}>{back}</div>
        <LoadingState className={styles.loading} size="default" />
      </div>
    );
  }

  const badge = pageBadge(page);
  const words = page.chunks.reduce((sum, chunk) => sum + chunk.word_count, 0);
  const external = page.url.startsWith("http");

  return (
    <div className={styles.reader}>
      <header className={styles.head}>
        {back}
        <div className={styles.titleRow}>
          <div className={styles.titleBlock}>
            <div className={styles.titleLine}>
              <h2 className={styles.title}>{page.title || shortAddress(page.url)}</h2>
              <StatusBadge status={badge.status} label={badge.label} />
            </div>
            {external ? (
              <a className={styles.address} href={page.url} target="_blank" rel="noreferrer">
                {shortAddress(page.url)} <ExternalLink className={styles.linkIcon} aria-hidden="true" />
              </a>
            ) : (
              <p className={styles.address}>{page.url}</p>
            )}
          </div>
          <div className={styles.actions}>
            {focus && (
              <Button variant="outline" size="sm" className={styles.focusButton} onClick={focus.toggle}>
                {focus.on ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                {focus.on ? "Show list" : "Focus reading"}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => copy("page", pageAsMarkdown(page.title || page.url, page.url, page.chunks))}
            >
              <Copy className="h-4 w-4" />
              {copied === "page" ? "Copied" : "Copy as Markdown"}
            </Button>
          </div>
        </div>

        <dl className={styles.facts}>
          <div>
            <dt>Chunks</dt>
            <dd>{page.chunk_count}</dd>
          </div>
          <div>
            <dt>Words</dt>
            <dd>{words.toLocaleString("en")}</dd>
          </div>
          <div>
            <dt>Read</dt>
            <dd>{relativeAge(page.last_read_at)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{page.source === "upload" ? "Upload" : "Crawl"}</dd>
          </div>
        </dl>

        {page.chunks.length > 0 && (
          <>
            <div className={styles.map} role="group" aria-label="Chunk map: each block is a chunk, as wide as its words. Choose one to jump to it.">
              {page.chunks.map((chunk) => (
                <button
                  key={chunk.chunk_id}
                  type="button"
                  className={`${styles.mapBlock} ${styles[MAP_CLASS[chunk.level] ?? "mapSection"]} ${hot === chunk.chunk_id ? styles.hot : ""}`}
                  style={{ flexGrow: Math.max(chunk.word_count, 8) }}
                  title={`${chunk.section_heading || chunkLevel(chunk)} • ${chunk.word_count} words`}
                  aria-label={`${chunk.section_heading || chunkLevel(chunk)}, ${chunk.word_count} words`}
                  onClick={() => jump(chunk)}
                />
              ))}
            </div>
            <p className={styles.legend}>
              <span className={styles.keyPage}>Whole page</span>
              <span className={styles.keySection}>Section</span>
              <span className={styles.keyParagraph}>Paragraph</span>
              Wider blocks hold more words. Very small or very large ones search poorly.
            </p>
          </>
        )}
      </header>

      <div className={styles.body}>
        {page.state === "failing" && (
          <div className={styles.notice} role="status">
            <b>
              Couldn't read this page in {page.consecutive_failures === 1 ? "the last crawl" : `the last ${page.consecutive_failures} crawls`}: {page.reason}.
            </b>
            <span>Agents still use the last good read from {relativeAge(page.last_read_at)}.</span>
          </div>
        )}
        {page.state === "gone" && (
          <div className={`${styles.notice} ${styles.noticeError}`} role="status">
            <b>The site no longer serves this page ({page.reason}).</b>
            <span>It was removed from search.</span>
          </div>
        )}
        {page.state === "duplicate" && (
          <div className={styles.notice} role="status">
            <b>Says what {shortAddress(page.duplicate_of)} says.</b>
            <span>
              Only that page is searched, so agents don't quote the same thing twice.{" "}
              <Button variant="link" size="sm" onClick={() => onOpenPage(page.duplicate_of)}>
                Open it
              </Button>
            </span>
          </div>
        )}
        {page.description && <p className={styles.description}>{page.description}</p>}

        {page.chunks.length > 0 && (
          <>
            <div className={styles.tools}>
              <div className={styles.seg} role="group" aria-label="How to show the page">
                <Button size="sm" variant={view === "chunks" ? "secondary" : "ghost"} aria-pressed={view === "chunks"} onClick={() => setView("chunks")}>
                  Chunks <span className={styles.hideNarrow}>as search sees them</span>
                </Button>
                <Button size="sm" variant={view === "read" ? "secondary" : "ghost"} aria-pressed={view === "read"} onClick={() => setView("read")}>
                  Reading view
                </Button>
              </div>
              {highlight && <span className={styles.hint}>Marking “{highlight}”</span>}
            </div>

            {view === "chunks" ? (
              <ol className={styles.chunks}>
                {page.chunks.map((chunk) => (
                  <li
                    key={chunk.chunk_id}
                    ref={(node) => {
                      if (node) chunkRefs.current.set(chunk.chunk_id, node);
                      else chunkRefs.current.delete(chunk.chunk_id);
                    }}
                    className={`${styles.chunk} ${hot === chunk.chunk_id ? styles.chunkHot : ""}`}
                  >
                    <div className={styles.chunkHead}>
                      <span className={`${styles.level} ${styles[LEVEL_CLASS[chunk.level] ?? "levelSection"]}`}>{chunkLevel(chunk)}</span>
                      {chunk.section_heading && <b className={styles.chunkHeading}>{chunk.section_heading}</b>}
                      <span>{chunk.word_count} words</span>
                      <span className={styles.chunkActions}>
                        <Button variant="ghost" size="sm" onClick={() => copy(chunk.chunk_id, chunk.content)}>
                          {copied === chunk.chunk_id ? "Copied" : "Copy"}
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => onAsk(`${chunk.section_heading} ${page.title}`.trim())}>
                          <MessageCircleQuestion className="h-4 w-4" />
                          <span className={styles.hideNarrow}>Ask about this</span>
                        </Button>
                      </span>
                    </div>
                    <p className={styles.chunkText}>
                      <Marked text={chunk.content} phrase={highlight} />
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <article className={styles.article}>
                {page.chunks.map((chunk) => (
                  <section key={chunk.chunk_id}>
                    {chunk.section_heading && <h3>{chunk.section_heading}</h3>}
                    {/* Marking a phrase needs the plain text; otherwise the chunk reads as the Markdown it is */}
                    {highlight ? (
                      <p>
                        <Marked text={chunk.content} phrase={highlight} />
                      </p>
                    ) : (
                      <MarkdownRenderer content={chunk.content} className={styles.markdown} />
                    )}
                  </section>
                ))}
              </article>
            )}
          </>
        )}

        {page.duplicates.length > 0 && (
          <div>
            <p className={styles.label}>Also says the same</p>
            <ul className={styles.addresses}>
              {page.duplicates.map((address) => (
                <li key={address}>
                  <Button variant="link" size="sm" onClick={() => onOpenPage(address)}>
                    {shortAddress(address)}
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
