import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ChevronLeft, Database, Pencil, Play, Upload } from "lucide-react";
import { Button, EmptyState, LoadingState, Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui";
import { Inline, Page, PageHeader } from "../../components/layout";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { knowledgeApiService } from "../../services/knowledge";
import type { CrawlJob, KnowledgeBase } from "../../types/knowledge";
import styles from "./KnowledgeBaseDetail.module.css";
import { EditKnowledgeBaseDialog } from "./knowledge-base/EditKnowledgeBaseDialog";
import { KnowledgeAsk } from "./knowledge-base/KnowledgeAsk";
import { KnowledgeInsights } from "./knowledge-base/KnowledgeInsights";
import { KnowledgeRuns } from "./knowledge-base/KnowledgeRuns";
import { PagesWorkspace } from "./knowledge-base/PagesWorkspace";
import { StartCrawlDialog } from "./knowledge-base/StartCrawlDialog";
import { UploadContentDialog } from "./knowledge-base/UploadContentDialog";
import { attentionItems, countByState, healthPercent, relativeAge } from "./knowledge-base/knowledgeWorkspace";
import { useKnowledgePages } from "./knowledge-base/useKnowledgePages";

const POLL_INTERVAL_MS = 5000;
// Crawl runs shown first, and added by each "Show older runs"
const RECENT_JOBS = 5;

const TABS = ["pages", "insights", "ask", "runs"] as const;
type TabName = (typeof TABS)[number];

export function KnowledgeBaseDetail() {
  const { kbId } = useParams<{ kbId: string }>();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const roomForTwoPanes = useMediaQuery("(min-width: 768px)");

  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [crawlJobs, setCrawlJobs] = useState<CrawlJob[]>([]);
  const [olderJobs, setOlderJobs] = useState<CrawlJob[]>([]);
  const [olderJobsCursor, setOlderJobsCursor] = useState<string | null>(null);
  const [loadingOlderJobs, setLoadingOlderJobs] = useState(false);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [crawlDialogOpen, setCrawlDialogOpen] = useState(false);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [uploadsRefreshKey, setUploadsRefreshKey] = useState(0);
  // Bumped when a document finishes indexing or is deleted, so the pages show what the index holds now
  const [indexChangedKey, setIndexChangedKey] = useState(0);
  const [askRequest, setAskRequest] = useState<{ question: string; at: number } | null>(null);

  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // Where the user is lives in the address, so a page can be linked to and the phone's back button closes a page
  const tab: TabName = TABS.find((name) => name === params.get("tab")) ?? "pages";
  const selectedUrl = params.get("page");
  const chunkId = params.get("chunk");
  const section = params.get("section");

  const go = useCallback(
    (changes: Record<string, string | null>, replace = true) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace }
      );
    },
    [setParams]
  );

  const selectPage = useCallback(
    // With the list beside the reader a choice just changes the reader; alone, it is a step the back button undoes
    (url: string | null) => go({ tab: null, page: url, chunk: null }, roomForTwoPanes),
    [go, roomForTwoPanes]
  );

  const loadKnowledgeBase = useCallback(async () => {
    if (!kbId) return;
    try {
      setError(null);
      setKb(await knowledgeApiService.getKnowledgeBase(kbId));
    } catch (err) {
      setError("Failed to load knowledge base. It may not exist or you don't have access.");
      console.error("Error loading knowledge base:", err);
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const pollJobProgress = useCallback(async () => {
    if (!kbId) return;
    try {
      const { items: jobs } = await knowledgeApiService.listCrawlJobs(kbId, RECENT_JOBS);
      setCrawlJobs(jobs);
      if (!jobs.some((job) => job.status === "in_progress")) {
        stopPolling();
        loadKnowledgeBase(); // the totals, now the crawl is done
      }
    } catch (err) {
      console.error("Error polling crawl jobs:", err);
    }
  }, [kbId, stopPolling, loadKnowledgeBase]);

  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return;
    setIsPolling(true);
    pollingIntervalRef.current = setInterval(pollJobProgress, POLL_INTERVAL_MS);
  }, [pollJobProgress]);

  const loadCrawlJobs = useCallback(async () => {
    if (!kbId) return;
    setLoadingJobs(true);
    try {
      const { items: jobs, next_cursor } = await knowledgeApiService.listCrawlJobs(kbId, RECENT_JOBS);
      setCrawlJobs(jobs);
      setOlderJobs([]);
      setOlderJobsCursor(next_cursor);
      const inProgress = jobs.some((job) => job.status === "in_progress");
      if (inProgress) startPolling();
      else stopPolling();
    } catch (err) {
      console.error("Error loading crawl jobs:", err);
    } finally {
      setLoadingJobs(false);
    }
  }, [kbId, startPolling, stopPolling]);

  const loadOlderJobs = async () => {
    if (!kbId || !olderJobsCursor) return;
    setLoadingOlderJobs(true);
    try {
      const { items, next_cursor } = await knowledgeApiService.listCrawlJobs(kbId, RECENT_JOBS, olderJobsCursor);
      setOlderJobs((jobs) => [...jobs, ...items]);
      setOlderJobsCursor(next_cursor);
    } catch (err) {
      console.error("Error loading older crawl jobs:", err);
    } finally {
      setLoadingOlderJobs(false);
    }
  };

  useEffect(() => {
    loadKnowledgeBase();
    loadCrawlJobs();
    return stopPolling;
    // Once per knowledge base
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId]);

  const handleCancelCrawl = async (jobId: string) => {
    if (!kbId) return;
    try {
      await knowledgeApiService.cancelCrawlJob(kbId, jobId);
      loadCrawlJobs();
    } catch (err) {
      console.error("Error cancelling crawl:", err);
    }
  };

  const handleRunJob = async (jobId: string) => {
    if (!kbId) return;
    try {
      await knowledgeApiService.runCrawlJob(kbId, jobId);
      startPolling();
      loadCrawlJobs();
    } catch (err) {
      console.error("Error running crawl job:", err);
    }
  };

  const handleCrawlStarted = (job: CrawlJob) => {
    setCrawlJobs((previous) => [job, ...previous]);
    setExpandedJobId(job.job_id);
    startPolling();
    go({ tab: "runs" });
  };

  // Files were accepted: they're read in the background, and the totals change only once each is indexed
  const handleUploaded = () => setUploadsRefreshKey((key) => key + 1);

  const handleIndexChanged = useCallback(() => {
    void loadKnowledgeBase();
    setIndexChangedKey((key) => key + 1);
  }, [loadKnowledgeBase]);

  // Changes when a crawl starts or ends or a document is indexed, so the pages show what the index holds now
  const pagesRefreshKey = `${crawlJobs.map((job) => `${job.job_id}:${job.status}`).join(",")}:${indexChangedKey}`;
  const { pages, truncated, error: pagesError } = useKnowledgePages(kbId ?? "", pagesRefreshKey);

  const summary = useMemo(() => {
    if (!pages) return null;
    return {
      health: healthPercent(countByState(pages)),
      issues: attentionItems(pages).length,
      failing: pages.filter((page) => page.state === "failing").length,
    };
  }, [pages]);
  const lastCrawl = crawlJobs.find((job) => job.status === "completed")?.timing.completed_at ?? null;

  if (loading) return <LoadingState />;

  if (error && !kb) {
    return (
      <Page>
        <PageHeader>
          <Inline gap="sm">
            <Button variant="ghost" size="icon" aria-label="Back" onClick={() => navigate("/dashboard/knowledge-bases")}>
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <h1 className={styles.title}>Knowledge Base Not Found</h1>
          </Inline>
        </PageHeader>
        <EmptyState
          icon={Database}
          title="Not Found"
          description={error}
          actionLabel="Back to Knowledge Bases"
          onAction={() => navigate("/dashboard/knowledge-bases")}
        />
      </Page>
    );
  }

  if (!kb) return null;

  return (
    <Page>
      <header className={styles.head}>
        <div className={styles.identity}>
          <Button variant="ghost" size="icon" aria-label="Back to knowledge bases" onClick={() => navigate("/dashboard/knowledge-bases")}>
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div className={styles.iconBox}>
            <Database className={styles.icon} />
          </div>
          <div className={styles.titleBlock}>
            <h1 className={styles.title}>{kb.name}</h1>
            <p className={styles.description} title={kb.description || undefined}>
              {kb.description || `${kb.total_pages} pages • ${kb.total_chunks} chunks`}
            </p>
          </div>
        </div>

        <div className={styles.actions}>
          <Button variant="outline" onClick={() => setEditing(true)}>
            <Pencil className="h-4 w-4" />
            Edit
          </Button>
          <Button variant="outline" onClick={() => setUploadDialogOpen(true)}>
            <Upload className="h-4 w-4" />
            Upload
          </Button>
          <Button onClick={() => setCrawlDialogOpen(true)}>
            <Play className="h-4 w-4" />
            Crawl site
          </Button>
        </div>

        <ul className={styles.kpis} aria-label="Knowledge base at a glance">
          <li className={`${styles.kpi} ${styles.health}`}>
            <span
              className={styles.ring}
              style={{ "--p": summary?.health ?? 0 } as React.CSSProperties}
              role="img"
              aria-label={summary?.health == null ? "No health yet" : `${summary.health}% of pages healthy`}
            >
              <i>{summary?.health ?? "–"}</i>
            </span>
            <span>
              <b>Health</b>
              <small>pages agents can use</small>
            </span>
          </li>
          <li className={styles.kpi}>
            <b>{kb.total_pages.toLocaleString()}</b>
            <small>pages</small>
          </li>
          <li className={styles.kpi}>
            <b>{kb.total_chunks.toLocaleString()}</b>
            <small>chunks searched</small>
          </li>
          <li className={`${styles.kpi} ${summary?.failing ? styles.warn : ""}`}>
            <b>{summary?.failing ?? "–"}</b>
            <small>need a look</small>
          </li>
          <li className={styles.kpi}>
            <b>{lastCrawl ? relativeAge(lastCrawl) : "Never"}</b>
            <small>last crawl finished</small>
          </li>
        </ul>
      </header>

      <Tabs value={tab} onValueChange={(next) => go({ tab: next === "pages" ? null : next })}>
        <TabsList className={styles.tabs}>
          <TabsTrigger value="pages">
            Pages <span className={styles.count}>{pages?.length ?? kb.total_pages}</span>
          </TabsTrigger>
          <TabsTrigger value="insights">
            Insights {!!summary?.issues && <span className={`${styles.count} ${styles.alert}`}>{summary.issues}</span>}
          </TabsTrigger>
          <TabsTrigger value="ask">Ask it</TabsTrigger>
          <TabsTrigger value="runs">Crawl history</TabsTrigger>
        </TabsList>

        {/* All four stay mounted, so a question and its answers are still there after a look at the pages */}
        <TabsContent value="pages" forceMount className={styles.panel}>
          <PagesWorkspace
            kbId={kb.kb_id}
            pages={pages}
            truncated={truncated}
            error={pagesError}
            refreshKey={pagesRefreshKey}
            selectedUrl={selectedUrl}
            chunkId={chunkId}
            section={section}
            onSelect={selectPage}
            onSection={(next) => go({ section: next })}
            onAsk={(question) => {
              setAskRequest({ question, at: Date.now() });
              go({ tab: "ask" });
            }}
          />
        </TabsContent>
        <TabsContent value="insights" forceMount className={styles.panel}>
          <KnowledgeInsights
            pages={pages}
            truncated={truncated}
            error={pagesError}
            onOpenPage={(url) => go({ tab: null, page: url, chunk: null }, false)}
            onOpenSection={(next) => go({ tab: null, section: next, page: null, chunk: null }, false)}
          />
        </TabsContent>
        <TabsContent value="ask" forceMount className={styles.panel}>
          <KnowledgeAsk
            kbId={kb.kb_id}
            pages={pages}
            request={askRequest}
            onOpenResult={(url, chunk) => go({ tab: null, page: url, chunk }, false)}
          />
        </TabsContent>
        <TabsContent value="runs" forceMount className={styles.panel}>
          <KnowledgeRuns
            kbId={kb.kb_id}
            jobs={[...crawlJobs, ...olderJobs]}
            loading={loadingJobs}
            polling={isPolling}
            hasOlder={olderJobsCursor !== null}
            loadingOlder={loadingOlderJobs}
            expandedJobId={expandedJobId}
            uploadsRefreshKey={uploadsRefreshKey}
            onIndexChanged={handleIndexChanged}
            onExpand={setExpandedJobId}
            onLoadOlder={loadOlderJobs}
            onCancel={handleCancelCrawl}
            onRun={handleRunJob}
            onStartCrawl={() => setCrawlDialogOpen(true)}
          />
        </TabsContent>
      </Tabs>

      <EditKnowledgeBaseDialog kb={kb} open={editing} onOpenChange={setEditing} onSaved={setKb} />
      <StartCrawlDialog kbId={kb.kb_id} open={crawlDialogOpen} onOpenChange={setCrawlDialogOpen} onStarted={handleCrawlStarted} />
      <UploadContentDialog kbId={kb.kb_id} open={uploadDialogOpen} onOpenChange={setUploadDialogOpen} onUploaded={handleUploaded} />
    </Page>
  );
}
