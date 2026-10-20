import { useMemo } from "react";
import { AlertTriangle, CheckCircle2, Copy, Hourglass } from "lucide-react";
import { AlertBanner, Button, InlineEmptyState, LoadingState } from "../../../components/ui";
import type { KnowledgePage } from "../../../types/knowledge";
import { shortAddress } from "./knowledgePageDetail";
import {
  attentionItems,
  countByState,
  freshness,
  healthPercent,
  pageSizes,
  sectionsOf,
  type Attention,
} from "./knowledgeWorkspace";
import styles from "./KnowledgeInsights.module.css";

interface KnowledgeInsightsProps {
  pages: KnowledgePage[] | null;
  truncated: boolean;
  error: string | null;
  onOpenPage: (url: string) => void;
  onOpenSection: (section: string) => void;
}

const KIND_ICON = { failing: AlertTriangle, duplicate: Copy, stale: Hourglass };
const SHOWN_ADDRESSES = 3;

const COVERAGE = [
  { state: "live", label: "Live", color: "var(--success)" },
  { state: "failing", label: "Couldn't read", color: "var(--warning)" },
  { state: "duplicate", label: "Duplicates", color: "var(--gradient-start)" },
  { state: "gone", label: "Removed", color: "var(--text-muted)" },
] as const;

/** How healthy the knowledge base is, how fresh, where its content is, and what the owner can fix. */
export function KnowledgeInsights({ pages, truncated, error, onOpenPage, onOpenSection }: KnowledgeInsightsProps) {
  const insights = useMemo(() => {
    if (!pages) return null;
    const counts = countByState(pages);
    return {
      counts,
      health: healthPercent(counts),
      buckets: freshness(pages),
      sizes: pageSizes(pages),
      attention: attentionItems(pages),
      sections: sectionsOf(pages),
    };
  }, [pages]);

  if (error && !pages) return <AlertBanner message={error} variant="error" />;
  if (!pages || !insights) return <LoadingState className={styles.loading} size="default" />;
  if (pages.length === 0) {
    return <InlineEmptyState icon={CheckCircle2} title="Nothing to show yet" description="Insights appear once the knowledge base has pages" />;
  }

  const { counts, buckets, sizes, attention, sections } = insights;
  const tallest = Math.max(1, ...buckets.map((bucket) => bucket.count));
  const biggest = sections[0].count;

  return (
    <div className={styles.grid}>
      {truncated && (
        <div className={styles.full}>
          <AlertBanner message="This knowledge base has more than 1,000 pages. These figures cover the first 1,000." variant="warning" />
        </div>
      )}

      <section className={styles.card}>
        <h3>Coverage</h3>
        <p className={styles.sub}>What happened to each page on the last crawl</p>
        <p className={styles.big}>
          {counts.live}
          <small> / {pages.length} live</small>
        </p>
        <div className={styles.stack} role="img" aria-label={`${counts.live} of ${pages.length} pages live`}>
          {COVERAGE.filter(({ state }) => counts[state] > 0).map(({ state, color }) => (
            <i key={state} style={{ flexGrow: counts[state], background: color }} />
          ))}
        </div>
        <ul className={styles.legend}>
          {COVERAGE.map(({ state, label, color }) => (
            <li key={state}>
              <span className={styles.swatch} style={{ background: color }} aria-hidden="true" />
              {label}
              <b>{counts[state]}</b>
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.card}>
        <h3>Freshness</h3>
        <p className={styles.sub}>How long ago each page was last read</p>
        <ul className={styles.bars}>
          {buckets.map((bucket) => (
            <li key={bucket.label}>
              <span>{bucket.count}</span>
              <i
                className={bucket.old ? styles.barOld : undefined}
                style={{ height: `${Math.max(4, (bucket.count / tallest) * 100)}%` }}
              />
              <span className={styles.barLabel}>{bucket.label}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.card}>
        <h3>Page size</h3>
        <p className={styles.sub}>Chunks per page that agents can search</p>
        <dl className={styles.table}>
          <div>
            <dt>Average</dt>
            <dd>{sizes.average}</dd>
          </div>
          <div>
            <dt>Single-chunk pages</dt>
            <dd className={sizes.thin ? styles.warn : undefined}>{sizes.thin}</dd>
          </div>
          <div>
            <dt>Large (20+ chunks)</dt>
            <dd className={sizes.large ? styles.warn : undefined}>{sizes.large}</dd>
          </div>
        </dl>
      </section>

      <section className={`${styles.card} ${styles.wide}`}>
        <h3>Needs a look</h3>
        <p className={styles.sub}>Fix these and agents answer better</p>
        {attention.length === 0 ? (
          <p className={styles.allGood}>
            <CheckCircle2 aria-hidden="true" /> Every page was read on the last crawl, and none is repeated or gone quiet.
          </p>
        ) : (
          <ul className={styles.issues}>
            {attention.map((item) => (
              <Issue key={`${item.kind}:${item.urls[0]}`} item={item} onOpenPage={onOpenPage} />
            ))}
          </ul>
        )}
      </section>

      <section className={`${styles.card} ${styles.narrow}`}>
        <h3>Where the knowledge is</h3>
        <p className={styles.sub}>Chunks per section of the site</p>
        <ul className={styles.sections}>
          {sections.map((section) => (
            <li key={section.id}>
              <Button variant="link" size="sm" onClick={() => onOpenSection(section.id)}>
                {section.id}
              </Button>
              <span>
                {section.count} {section.count === 1 ? "page" : "pages"}
              </span>
              <div className={styles.share} aria-hidden="true">
                <i style={{ width: `${(section.count / biggest) * 100}%` }} />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function Issue({ item, onOpenPage }: { item: Attention; onOpenPage: (url: string) => void }) {
  const Icon = KIND_ICON[item.kind];
  return (
    <li className={styles.issue}>
      <Icon className={item.kind === "failing" ? styles.iconWarn : styles.icon} aria-hidden="true" />
      <div className={styles.issueText}>
        <b>{item.title}</b>
        <span>{item.detail}</span>
        <span className={styles.addresses}>
          {item.urls.slice(0, SHOWN_ADDRESSES).map((url) => (
            <Button key={url} variant="link" size="sm" onClick={() => onOpenPage(url)}>
              {shortAddress(url)}
            </Button>
          ))}
          {item.urls.length > SHOWN_ADDRESSES && <span>and {item.urls.length - SHOWN_ADDRESSES} more</span>}
        </span>
      </div>
    </li>
  );
}
