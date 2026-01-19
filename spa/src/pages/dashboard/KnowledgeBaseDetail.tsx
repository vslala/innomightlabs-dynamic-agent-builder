import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Database,
  ChevronLeft,
  Pencil,
  Plus,
  Play,
  XCircle,
  Globe,
  ChevronDown,
  ChevronRight,
  Loader2,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Input,
  Label,
  Textarea,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  LoadingState,
  EmptyState,
  InlineEmptyState,
  StatusBadge,
  StatusIcon,
  StatItem,
  StatsGrid,
  ProgressBar,
  Pill,
  PillGroup,
  AlertBanner,
} from "../../components/ui";
import { ActivityLog, ActivityLogHeader } from "../../components/knowledge";
import { knowledgeApiService } from "../../services/knowledge";
import type {
  KnowledgeBase,
  CrawlJob,
  CrawlJobStatus,
  CrawlSourceType,
  CrawlEvent,
} from "../../types/knowledge";

export function KnowledgeBaseDetail() {
  const { kbId } = useParams<{ kbId: string }>();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [crawlJobs, setCrawlJobs] = useState<CrawlJob[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const [isStartCrawlDialogOpen, setIsStartCrawlDialogOpen] = useState(false);
  const [crawlSourceType, setCrawlSourceType] = useState<CrawlSourceType>("sitemap");
  const [crawlSourceUrl, setCrawlSourceUrl] = useState("");
  const [crawlMaxPages, setCrawlMaxPages] = useState(100);
  const [crawlMaxDepth, setCrawlMaxDepth] = useState(3);
  const [isStartingCrawl, setIsStartingCrawl] = useState(false);
  const [crawlError, setCrawlError] = useState<string | null>(null);

  const [activeEventSource, setActiveEventSource] = useState<EventSource | null>(null);
  const [crawlEvents, setCrawlEvents] = useState<Record<string, CrawlEvent[]>>({});
  const [isStreaming, setIsStreaming] = useState(false);
  const lastCursorRef = useRef<string | undefined>(undefined);

  const loadKnowledgeBase = async () => {
    if (!kbId) return;
    try {
      setError(null);
      const data = await knowledgeApiService.getKnowledgeBase(kbId);
      setKb(data);
      setEditName(data.name);
      setEditDescription(data.description || "");
    } catch (err) {
      setError(
        "Failed to load knowledge base. It may not exist or you don't have access."
      );
      console.error("Error loading knowledge base:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadCrawlJobs = useCallback(async () => {
    if (!kbId) return;
    setLoadingJobs(true);
    try {
      const jobs = await knowledgeApiService.listCrawlJobs(kbId, 10);
      setCrawlJobs(jobs);

      const inProgressJob = jobs.find((j) => j.status === "in_progress");
      if (inProgressJob && !activeEventSource) {
        startEventStream(inProgressJob.job_id);
      }
    } catch (err) {
      console.error("Error loading crawl jobs:", err);
    } finally {
      setLoadingJobs(false);
    }
  }, [kbId, activeEventSource]);

  const startEventStream = (jobId: string, cursor?: string) => {
    if (!kbId) return;

    if (activeEventSource) {
      activeEventSource.close();
    }

    setIsStreaming(true);

    const eventSource = knowledgeApiService.streamCrawlProgress(
      kbId,
      jobId,
      (event: CrawlEvent) => {
        if (event.event_type !== "JOB_PROGRESS") {
          setCrawlEvents((prev) => ({
            ...prev,
            [jobId]: [...(prev[jobId] || []), event],
          }));
        }

        if (event.cursor) {
          lastCursorRef.current = event.cursor;
        }

        setCrawlJobs((prev) =>
          prev.map((job) => {
            if (job.job_id === event.job_id && event.progress) {
              return {
                ...job,
                status: event.status || job.status,
                progress: event.progress,
              };
            }
            return job;
          })
        );

        if (event.event_type === "JOB_COMPLETED" || event.event_type === "JOB_FAILED") {
          eventSource.close();
          setActiveEventSource(null);
          setIsStreaming(false);
          loadCrawlJobs();
          loadKnowledgeBase();
        }
      },
      (err) => {
        console.error("SSE error:", err);
        eventSource.close();
        setActiveEventSource(null);
        setIsStreaming(false);
      },
      cursor
    );

    setActiveEventSource(eventSource);
  };

  useEffect(() => {
    loadKnowledgeBase();
    loadCrawlJobs();
    return () => {
      if (activeEventSource) {
        activeEventSource.close();
      }
    };
  }, [kbId]);

  const handleUpdate = async () => {
    if (!kbId || !editName.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const updated = await knowledgeApiService.updateKnowledgeBase(kbId, {
        name: editName.trim(),
        description: editDescription.trim() || undefined,
      });
      setKb(updated);
      setIsEditing(false);
    } catch (err) {
      setError("Failed to update knowledge base. Please try again.");
      console.error("Error updating knowledge base:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStartCrawl = async () => {
    if (!kbId || !crawlSourceUrl.trim()) return;
    setIsStartingCrawl(true);
    setCrawlError(null);
    try {
      const job = await knowledgeApiService.startCrawlJob(kbId, {
        source_type: crawlSourceType,
        source_url: crawlSourceUrl.trim(),
        max_pages: crawlMaxPages,
        max_depth: crawlMaxDepth,
      });

      setCrawlJobs((prev) => [job, ...prev]);
      setExpandedJobId(job.job_id);
      startEventStream(job.job_id);
      setIsStartCrawlDialogOpen(false);
      setCrawlSourceUrl("");
      setCrawlError(null);
    } catch (err: unknown) {
      console.error("Error starting crawl:", err);
      let errorMessage = "Failed to start crawl. Please try again.";
      if (err instanceof Error) {
        errorMessage = err.message;
      } else if (typeof err === "object" && err !== null) {
        const errorObj = err as Record<string, unknown>;
        if (typeof errorObj.detail === "string") {
          errorMessage = errorObj.detail;
        } else if (typeof errorObj.message === "string") {
          errorMessage = errorObj.message;
        }
      }
      setCrawlError(errorMessage);
    } finally {
      setIsStartingCrawl(false);
    }
  };

  const handleCancelCrawl = async (jobId: string) => {
    if (!kbId) return;
    try {
      await knowledgeApiService.cancelCrawlJob(kbId, jobId);
      loadCrawlJobs();
    } catch (err) {
      console.error("Error cancelling crawl:", err);
    }
  };

  const mapStatus = (status: CrawlJobStatus) => status as "pending" | "in_progress" | "completed" | "failed" | "cancelled";

  const formatDate = (dateString: string | null) => {
    if (!dateString) return "—";
    return new Date(dateString).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatDuration = (ms: number | null) => {
    if (!ms) return "—";
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  if (loading) {
    return <LoadingState />;
  }

  if (error && !kb) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/knowledge-bases")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            Knowledge Base Not Found
          </h1>
        </div>
        <EmptyState
          icon={Database}
          title="Not Found"
          description={error}
          actionLabel="Back to Knowledge Bases"
          onAction={() => navigate("/dashboard/knowledge-bases")}
        />
      </div>
    );
  }

  if (!kb) return null;

  return (
    <div
      style={{
        maxWidth: "48rem",
        display: "flex",
        flexDirection: "column",
        gap: "2rem",
      }}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/knowledge-bases")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)] flex items-center justify-center">
            <Database className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">
              {kb.name}
            </h1>
            <p className="text-sm text-[var(--text-muted)]">
              {kb.total_pages} pages • {kb.total_chunks} chunks
            </p>
          </div>
        </div>
        {!isEditing && (
          <Button variant="outline" onClick={() => setIsEditing(true)}>
            <Pencil className="h-4 w-4 mr-2" />
            Edit
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {isEditing ? "Edit Knowledge Base" : "Details"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}

          {isEditing ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={3}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsEditing(false);
                    setEditName(kb.name);
                    setEditDescription(kb.description || "");
                  }}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleUpdate}
                  disabled={isSubmitting || !editName.trim()}
                >
                  {isSubmitting ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <Label className="text-[var(--text-muted)]">Description</Label>
                <p className="text-[var(--text-primary)] mt-1">
                  {kb.description || "No description"}
                </p>
              </div>

              <div className="grid grid-cols-3 gap-4 pt-4 border-t border-[var(--border-subtle)]">
                <div>
                  <Label className="text-[var(--text-muted)]">Pages</Label>
                  <p className="text-lg font-semibold text-[var(--text-primary)]">
                    {kb.total_pages.toLocaleString()}
                  </p>
                </div>
                <div>
                  <Label className="text-[var(--text-muted)]">Chunks</Label>
                  <p className="text-lg font-semibold text-[var(--text-primary)]">
                    {kb.total_chunks.toLocaleString()}
                  </p>
                </div>
                <div>
                  <Label className="text-[var(--text-muted)]">Vectors</Label>
                  <p className="text-lg font-semibold text-[var(--text-primary)]">
                    {kb.total_vectors.toLocaleString()}
                  </p>
                </div>
              </div>

              <div className="pt-4 border-t border-[var(--border-subtle)] text-sm text-[var(--text-muted)]">
                Created {formatDate(kb.created_at)}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-[var(--gradient-start)]" />
              <CardTitle className="text-lg">Web Crawl Jobs</CardTitle>
            </div>
            <Button size="sm" onClick={() => setIsStartCrawlDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-1.5" />
              Start Crawl
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loadingJobs ? (
            <LoadingState className="h-32" size="default" />
          ) : crawlJobs.length === 0 ? (
            <InlineEmptyState
              icon={Globe}
              title="No crawl jobs yet"
              description="Start a crawl to import content from a website"
            />
          ) : (
            <div className="space-y-3">
              {crawlJobs.map((job) => (
                <div
                  key={job.job_id}
                  className="border border-[var(--border-subtle)] rounded-lg overflow-hidden"
                >
                  <div
                    className="flex items-center justify-between p-4 cursor-pointer hover:bg-white/5"
                    onClick={() =>
                      setExpandedJobId(expandedJobId === job.job_id ? null : job.job_id)
                    }
                  >
                    <div className="flex items-center gap-3">
                      {expandedJobId === job.job_id ? (
                        <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-[var(--text-muted)]" />
                      )}
                      <StatusIcon status={mapStatus(job.status)} />
                      <div>
                        <p className="font-medium text-[var(--text-primary)]">
                          {job.config.source_url}
                        </p>
                        <p className="text-xs text-[var(--text-muted)]">
                          {job.config.source_type} • {formatDate(job.created_at)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge status={mapStatus(job.status)} />
                      {job.status === "in_progress" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 hover:text-red-300"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCancelCrawl(job.job_id);
                          }}
                        >
                          <XCircle className="h-4 w-4" />
                        </Button>
                      )}
                      {job.status === "pending" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-green-400 hover:text-green-300"
                          onClick={async (e) => {
                            e.stopPropagation();
                            await knowledgeApiService.runCrawlJob(kbId!, job.job_id);
                            startEventStream(job.job_id);
                            loadCrawlJobs();
                          }}
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>

                  {expandedJobId === job.job_id && (
                    <div className="border-t border-[var(--border-subtle)] p-4 bg-[var(--bg-secondary)]">
                      {(job.status === "in_progress" || job.status === "completed") && (
                        <ProgressBar
                          value={job.progress.processed_urls}
                          max={job.progress.discovered_urls}
                          label="Progress"
                          className="mb-4"
                        />
                      )}

                      <StatsGrid columns={4}>
                        <StatItem label="Discovered" value={job.progress.discovered_urls} />
                        <StatItem label="Processed" value={job.progress.processed_urls} />
                        <StatItem label="Success" value={job.progress.successful_urls} valueClassName="text-green-400" />
                        <StatItem label="Failed" value={job.progress.failed_urls} valueClassName="text-red-400" />
                      </StatsGrid>

                      <StatsGrid columns={4} className="mt-4">
                        <StatItem label="Chunks" value={job.progress.total_chunks} />
                        <StatItem label="Embeddings" value={job.progress.total_embeddings} />
                        <StatItem label="Duration" value={formatDuration(job.timing.total_duration_ms)} />
                        <StatItem label="Avg/Page" value={formatDuration(job.timing.avg_page_duration_ms)} />
                      </StatsGrid>

                      {job.error_message && (
                        <AlertBanner message={job.error_message} variant="error" className="mt-4" />
                      )}

                      {(job.status === "in_progress" || crawlEvents[job.job_id]?.length > 0) && (
                        <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
                          <ActivityLogHeader
                            eventCount={crawlEvents[job.job_id]?.length || 0}
                            isStreaming={isStreaming && job.status === "in_progress"}
                          />
                          <ActivityLog
                            events={crawlEvents[job.job_id] || []}
                            maxHeight="300px"
                            className="mt-2 border border-[var(--border-subtle)] rounded-lg bg-[var(--bg-primary)]"
                          />
                        </div>
                      )}

                      <div className="mt-4 pt-4 border-t border-[var(--border-subtle)]">
                        <p className="text-xs text-[var(--text-muted)] mb-2">Configuration</p>
                        <PillGroup>
                          <Pill>Max Pages: {job.config.max_pages}</Pill>
                          <Pill>Max Depth: {job.config.max_depth}</Pill>
                          <Pill>Rate Limit: {job.config.rate_limit_ms}ms</Pill>
                        </PillGroup>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={isStartCrawlDialogOpen}
        onOpenChange={(open) => {
          setIsStartCrawlDialogOpen(open);
          if (!open) {
            setCrawlError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start Web Crawl</DialogTitle>
            <DialogDescription>
              Crawl a website to import its content into this knowledge base.
            </DialogDescription>
          </DialogHeader>

          {crawlError && (
            <AlertBanner message={crawlError} variant="error" className="mx-1 my-2" />
          )}

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="source-type">Source Type</Label>
              <Select
                value={crawlSourceType}
                onValueChange={(v) => setCrawlSourceType(v as CrawlSourceType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="sitemap">Sitemap URL</SelectItem>
                  <SelectItem value="url">Starting URL</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-[var(--text-muted)]">
                {crawlSourceType === "sitemap"
                  ? "Provide a sitemap.xml URL to crawl all listed pages"
                  : "Provide a starting URL to crawl and follow links"}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="source-url">
                {crawlSourceType === "sitemap" ? "Sitemap URL" : "Starting URL"}
              </Label>
              <Input
                id="source-url"
                value={crawlSourceUrl}
                onChange={(e) => setCrawlSourceUrl(e.target.value)}
                placeholder={
                  crawlSourceType === "sitemap"
                    ? "https://example.com/sitemap.xml"
                    : "https://example.com/docs"
                }
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="max-pages">Max Pages</Label>
                <Input
                  id="max-pages"
                  type="number"
                  min={1}
                  max={1000}
                  value={crawlMaxPages}
                  onChange={(e) =>
                    setCrawlMaxPages(parseInt(e.target.value) || 100)
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max-depth">Max Depth</Label>
                <Input
                  id="max-depth"
                  type="number"
                  min={1}
                  max={10}
                  value={crawlMaxDepth}
                  onChange={(e) =>
                    setCrawlMaxDepth(parseInt(e.target.value) || 3)
                  }
                />
                <p className="text-xs text-[var(--text-muted)]">Only for URL crawling</p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsStartCrawlDialogOpen(false)}
              disabled={isStartingCrawl}
            >
              Cancel
            </Button>
            <Button
              onClick={handleStartCrawl}
              disabled={isStartingCrawl || !crawlSourceUrl.trim()}
            >
              {isStartingCrawl ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Start Crawl
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
