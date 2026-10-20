import { Globe, Loader2, Play, Plus, RotateCcw, XCircle } from "lucide-react";
import {
  AlertBanner,
  Button,
  ExpandableCard,
  InlineEmptyState,
  LoadingState,
  Pill,
  PillGroup,
  ProgressBar,
  StatItem,
  StatsGrid,
  StatusBadge,
  StatusIcon,
} from "../../../components/ui";
import type { CrawlJob, CrawlJobStatus } from "../../../types/knowledge";
import { formatDate, formatDuration } from "./knowledgeFormat";
import { KnowledgeUploads } from "./KnowledgeUploads";
import styles from "./KnowledgeRuns.module.css";

interface KnowledgeRunsProps {
  kbId: string;
  jobs: CrawlJob[];
  loading: boolean;
  polling: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  expandedJobId: string | null;
  uploadsRefreshKey: number;
  onExpand: (jobId: string | null) => void;
  onLoadOlder: () => void;
  onCancel: (jobId: string) => void;
  onRun: (jobId: string) => void;
  onStartCrawl: () => void;
}

const mapStatus = (status: CrawlJobStatus) => status as "pending" | "in_progress" | "completed" | "failed" | "cancelled";

function progressPercent(job: CrawlJob): number {
  const { discovered_urls, processed_urls } = job.progress;
  return discovered_urls === 0 ? 0 : Math.round((processed_urls / discovered_urls) * 100);
}

/** What a run did to the pages, in the order a reader cares: what changed, what didn't, what went wrong. */
function outcomes(job: CrawlJob): { label: string; tone: "changed" | "same" | "removed" | "failed" }[] {
  const { successful_urls, unchanged_urls, duplicate_urls, removed_urls, failed_urls } = job.progress;
  const updated = Math.max(0, successful_urls - unchanged_urls - duplicate_urls);
  return [
    { label: `${updated} read and updated`, tone: "changed" as const, n: updated },
    { label: `${unchanged_urls} unchanged`, tone: "same" as const, n: unchanged_urls },
    { label: `${duplicate_urls} duplicates`, tone: "same" as const, n: duplicate_urls },
    { label: `${removed_urls} removed`, tone: "removed" as const, n: removed_urls },
    { label: `${failed_urls} failed`, tone: "failed" as const, n: failed_urls },
  ].filter((outcome) => outcome.n > 0);
}

const TONE_CLASS = { changed: "toneChanged", same: "toneSame", removed: "toneRemoved", failed: "toneFailed" } as const;

/** Every crawl, newest first, and the files uploaded. */
export function KnowledgeRuns({
  kbId,
  jobs,
  loading,
  polling,
  hasOlder,
  loadingOlder,
  expandedJobId,
  uploadsRefreshKey,
  onExpand,
  onLoadOlder,
  onCancel,
  onRun,
  onStartCrawl,
}: KnowledgeRunsProps) {
  return (
    <div className={styles.runs}>
      <section className={styles.section}>
        <div className={styles.sectionHead}>
          <h2>
            Crawl history {polling && <Loader2 className={styles.spinner} aria-label="Updating" />}
          </h2>
          <Button size="sm" onClick={onStartCrawl}>
            <Plus className="h-4 w-4" />
            Start crawl
          </Button>
        </div>

        {loading ? (
          <LoadingState className={styles.loading} size="default" />
        ) : jobs.length === 0 ? (
          <InlineEmptyState icon={Globe} title="No crawls yet" description="Start a crawl to import content from a website" />
        ) : (
          <ol className={styles.timeline}>
            {jobs.map((job) => (
              <li key={job.job_id} className={styles.run}>
                <span className={`${styles.dot} ${job.status === "failed" ? styles.dotFailed : ""}`} aria-hidden="true" />
                <ExpandableCard
                  expanded={expandedJobId === job.job_id}
                  onToggle={() => onExpand(expandedJobId === job.job_id ? null : job.job_id)}
                  header={
                    <div className={styles.header}>
                      <div className={styles.headerMain}>
                        <StatusIcon status={mapStatus(job.status)} />
                        <div className={styles.titleWrap}>
                          <p className={styles.url}>{job.config.source_url}</p>
                          <p className={styles.meta}>
                            {job.config.source_type} • {formatDate(job.timing.started_at ?? job.created_at)}
                            {job.timing.total_duration_ms ? ` • ${formatDuration(job.timing.total_duration_ms)}` : ""}
                          </p>
                        </div>
                      </div>
                      <div className={styles.headerSide}>
                        {job.status === "in_progress" && <span className={styles.percent}>{progressPercent(job)}%</span>}
                        <StatusBadge status={mapStatus(job.status)} />
                        {job.status === "in_progress" && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className={styles.cancel}
                            aria-label="Cancel crawl"
                            onClick={(event) => {
                              event.stopPropagation();
                              onCancel(job.job_id);
                            }}
                          >
                            <XCircle className="h-4 w-4" />
                          </Button>
                        )}
                        {(job.status === "pending" || job.status === "failed") && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className={styles.retry}
                            aria-label={job.status === "pending" ? "Run crawl" : "Retry crawl"}
                            title={
                              job.status === "failed" && job.checkpoint && job.checkpoint.pending_urls.length > 0
                                ? `Retry (resumes from page ${job.checkpoint.current_url_index} of ${job.checkpoint.pending_urls.length})`
                                : undefined
                            }
                            onClick={(event) => {
                              event.stopPropagation();
                              onRun(job.job_id);
                            }}
                          >
                            {job.status === "pending" ? <Play className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />}
                          </Button>
                        )}
                      </div>
                      {job.status !== "in_progress" && job.status !== "pending" && (
                        <div className={styles.chips}>
                          {outcomes(job).map((outcome) => (
                            <span key={outcome.label} className={`${styles.chip} ${styles[TONE_CLASS[outcome.tone]]}`}>
                              {outcome.label}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  }
                >
                  <div className={styles.details}>
                    {(job.status === "in_progress" || job.status === "completed") && (
                      <div>
                        <div className={styles.progressHead}>
                          <span>{job.status === "in_progress" ? "Crawling..." : "Completed"}</span>
                          <b>
                            {job.progress.processed_urls} / {job.progress.discovered_urls} pages
                          </b>
                        </div>
                        <ProgressBar value={job.progress.processed_urls} max={job.progress.discovered_urls || 1} />
                      </div>
                    )}

                    <StatsGrid columns={2}>
                      <StatItem label="Discovered" value={job.progress.discovered_urls} />
                      <StatItem label="Success" value={job.progress.successful_urls} valueClassName={styles.good} />
                      <StatItem label="Failed" value={job.progress.failed_urls} valueClassName={styles.bad} />
                      <StatItem label="Removed" value={job.progress.removed_urls} />
                      <StatItem label="Chunks" value={job.progress.total_chunks} />
                      <StatItem label="Embeddings" value={job.progress.total_embeddings} />
                      <StatItem label="Duration" value={formatDuration(job.timing.total_duration_ms)} />
                      <StatItem label="Avg/Page" value={formatDuration(job.timing.avg_page_duration_ms)} />
                    </StatsGrid>

                    {job.error_message && <AlertBanner message={job.error_message} variant="error" />}

                    {job.status === "failed" && job.checkpoint && job.checkpoint.pending_urls.length > 0 && (
                      <p className={styles.hint}>
                        Retrying will resume from page {job.checkpoint.current_url_index} of {job.checkpoint.pending_urls.length}{" "}
                        instead of starting over.
                      </p>
                    )}

                    <div>
                      <p className={styles.hint}>Configuration</p>
                      <PillGroup>
                        <Pill variant="outline">Max Pages: {job.config.max_pages}</Pill>
                        <Pill variant="outline">Max Depth: {job.config.max_depth}</Pill>
                        <Pill variant="outline">Rate Limit: {job.config.rate_limit_ms}ms</Pill>
                      </PillGroup>
                    </div>
                  </div>
                </ExpandableCard>
              </li>
            ))}
          </ol>
        )}
        {hasOlder && (
          <Button variant="outline" size="sm" onClick={onLoadOlder} disabled={loadingOlder}>
            {loadingOlder ? "Loading..." : "Show older runs"}
          </Button>
        )}
      </section>

      <KnowledgeUploads kbId={kbId} refreshKey={uploadsRefreshKey} />
    </div>
  );
}
