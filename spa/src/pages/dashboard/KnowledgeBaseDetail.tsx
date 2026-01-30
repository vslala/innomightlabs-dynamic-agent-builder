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
  FileText,
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
import { SchemaForm } from "../../components/forms";
import { knowledgeApiService } from "../../services/knowledge";
import { KB_UPLOAD_ALLOWED_EXTENSIONS, KB_UPLOAD_MAX_FILE_SIZE } from "../../types/knowledge";
import type {
  KnowledgeBase,
  CrawlJob,
  CrawlJobStatus,
  CrawlSourceType,
  ContentUploadResponse,
  ContentUploadItem,
} from "../../types/knowledge";
import type { FormSchema, FormValue } from "../../types/form";
import styles from "./KnowledgeBaseDetail.module.css";

const POLL_INTERVAL_MS = 5000; // 5 seconds

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

  const [contentUploadSchema, setContentUploadSchema] = useState<FormSchema | null>(null);
  const [loadingContentSchema, setLoadingContentSchema] = useState(false);
  const [contentUploadError, setContentUploadError] = useState<string | null>(null);
  const [contentUploadNotice, setContentUploadNotice] = useState<string | null>(null);
  const [isUploadingContent, setIsUploadingContent] = useState(false);
  const [contentFormKey, setContentFormKey] = useState(0);

  const [uploads, setUploads] = useState<ContentUploadItem[]>([]);
  const [uploadsCursor, setUploadsCursor] = useState<string | null>(null);
  const [hasMoreUploads, setHasMoreUploads] = useState(false);
  const [loadingUploads, setLoadingUploads] = useState(false);
  const [uploadsError, setUploadsError] = useState<string | null>(null);

  // Polling state
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isPolling, setIsPolling] = useState(false);

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

      // Check if any job is in progress and start polling
      const hasInProgressJob = jobs.some((j) => j.status === "in_progress");
      if (hasInProgressJob && !pollingIntervalRef.current) {
        startPolling();
      } else if (!hasInProgressJob && pollingIntervalRef.current) {
        stopPolling();
      }
    } catch (err) {
      console.error("Error loading crawl jobs:", err);
    } finally {
      setLoadingJobs(false);
    }
  }, [kbId]);

  const loadContentUploadSchema = useCallback(async () => {
    if (!kbId) return;
    setLoadingContentSchema(true);
    try {
      const schema = await knowledgeApiService.getContentUploadSchema(kbId);
      setContentUploadSchema(schema);
    } catch (err) {
      console.error("Error loading content upload schema:", err);
      setContentUploadError("Failed to load content upload form.");
    } finally {
      setLoadingContentSchema(false);
    }
  }, [kbId]);

  const loadUploads = useCallback(
    async (options?: { cursor?: string | null; reset?: boolean }) => {
      if (!kbId) return;
      setLoadingUploads(true);
      setUploadsError(null);
      try {
        const response = await knowledgeApiService.listContentUploads(
          kbId,
          10,
          options?.cursor
        );
        setUploads((prev) => {
          const merged = options?.reset ? response.items : [...prev, ...response.items];
          return [...merged].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          );
        });
        setUploadsCursor(response.next_cursor);
        setHasMoreUploads(response.has_more);
      } catch (err) {
        console.error("Error loading uploads:", err);
        setUploadsError("Failed to load uploads.");
      } finally {
        setLoadingUploads(false);
      }
    },
    [kbId]
  );

  const pollJobProgress = useCallback(async () => {
    if (!kbId) return;

    try {
      const jobs = await knowledgeApiService.listCrawlJobs(kbId, 10);
      setCrawlJobs(jobs);

      // Check if any job is still in progress
      const hasInProgressJob = jobs.some((j) => j.status === "in_progress");
      if (!hasInProgressJob) {
        stopPolling();
        // Refresh KB stats when all jobs complete
        loadKnowledgeBase();
      }
    } catch (err) {
      console.error("Error polling crawl jobs:", err);
    }
  }, [kbId]);

  const startPolling = useCallback(() => {
    if (pollingIntervalRef.current) return; // Already polling

    setIsPolling(true);
    pollingIntervalRef.current = setInterval(() => {
      pollJobProgress();
    }, POLL_INTERVAL_MS);
  }, [pollJobProgress]);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  useEffect(() => {
    loadKnowledgeBase();
    loadCrawlJobs();
    loadContentUploadSchema();
    loadUploads({ reset: true });

    return () => {
      // Cleanup polling on unmount
      stopPolling();
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
      startPolling(); // Start polling for progress
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

  const handleRunPendingJob = async (jobId: string) => {
    if (!kbId) return;
    try {
      await knowledgeApiService.runCrawlJob(kbId, jobId);
      startPolling();
      loadCrawlJobs();
    } catch (err) {
      console.error("Error running crawl job:", err);
    }
  };

  const getFileExtension = (filename: string) => {
    const idx = filename.lastIndexOf(".");
    return idx >= 0 ? filename.slice(idx).toLowerCase() : "";
  };

  const validateFilesForUpload = (files: File[]) => {
    for (const file of files) {
      const ext = getFileExtension(file.name);
      if (!KB_UPLOAD_ALLOWED_EXTENSIONS.includes(ext)) {
        return `File type '${ext || "unknown"}' is not supported.`;
      }
      if (file.size > KB_UPLOAD_MAX_FILE_SIZE) {
        return `${file.name} exceeds 5MB per file limit.`;
      }
    }
    return null;
  };

  const handleContentUpload = async (data: Record<string, FormValue>) => {
    if (!kbId) return;

    const metadata = typeof data.metadata === "string" ? data.metadata.trim() : "";
    const attachmentValue = data.attachment;
    const files = attachmentValue instanceof FileList
      ? Array.from(attachmentValue)
      : Array.isArray(attachmentValue)
        ? attachmentValue
        : [];

    if (files.length === 0) {
      setContentUploadError("Select at least one file to upload.");
      return;
    }

    const validationError = validateFilesForUpload(files);
    if (validationError) {
      setContentUploadError(validationError);
      return;
    }

    setIsUploadingContent(true);
    setContentUploadError(null);
    setContentUploadNotice(null);

    let uploadedCount = 0;
    let lastResponse: ContentUploadResponse | null = null;

    try {
      for (const file of files) {
        lastResponse = await knowledgeApiService.uploadContentFile(kbId, {
          file,
          metadata: metadata || undefined,
        });
        uploadedCount += 1;
      }

      if (uploadedCount > 0) {
        setContentUploadNotice(`Uploaded ${uploadedCount} file${uploadedCount === 1 ? "" : "s"} successfully.`);
        setContentFormKey((prev) => prev + 1);
        if (lastResponse) {
          setKb((prev) =>
            prev
              ? {
                ...prev,
                total_pages: lastResponse.total_pages,
                total_chunks: lastResponse.total_chunks,
                total_vectors: lastResponse.total_vectors,
              }
              : prev
          );
        }
        loadUploads({ reset: true });
      }
    } catch (err: unknown) {
      console.error("Error uploading content:", err);
      if (err instanceof Error) {
        setContentUploadError(err.message);
      } else {
        setContentUploadError("Failed to upload content. Please try again.");
      }
    } finally {
      setIsUploadingContent(false);
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getProgressPercentage = (job: CrawlJob) => {
    if (job.progress.discovered_urls === 0) return 0;
    return Math.round((job.progress.processed_urls / job.progress.discovered_urls) * 100);
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
        <CardContent className={styles.uploadsContent}>
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
              {isPolling && (
                <Loader2 className="h-4 w-4 animate-spin text-[var(--text-muted)]" />
              )}
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
                      {job.status === "in_progress" && (
                        <span className="text-xs text-[var(--text-muted)]">
                          {getProgressPercentage(job)}%
                        </span>
                      )}
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
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRunPendingJob(job.job_id);
                          }}
                        >
                          <Play className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>

                  {expandedJobId === job.job_id && (
                    <div className="border-t border-[var(--border-subtle)] p-4 bg-[var(--bg-secondary)]">
                      {/* Progress bar for in-progress and completed jobs */}
                      {(job.status === "in_progress" || job.status === "completed") && (
                        <div className="mb-4">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-[var(--text-muted)]">
                              {job.status === "in_progress" ? "Crawling..." : "Completed"}
                            </span>
                            <span className="text-sm font-medium text-[var(--text-primary)]">
                              {job.progress.processed_urls} / {job.progress.discovered_urls} pages
                            </span>
                          </div>
                          <ProgressBar
                            value={job.progress.processed_urls}
                            max={job.progress.discovered_urls || 1}
                          />
                        </div>
                      )}

                      {/* Stats grid */}
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

                      {/* Error message */}
                      {job.error_message && (
                        <AlertBanner message={job.error_message} variant="error" className="mt-4" />
                      )}

                      {/* Configuration */}
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

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Database className="h-5 w-5 text-[var(--gradient-start)]" />
            <CardTitle className="text-lg">Upload Content</CardTitle>
          </div>
        </CardHeader>
        <CardContent className={styles.uploadContent}>
          <p className={styles.uploadLead}>
            Upload text-based files (max 5MB per file). Multiple files will upload one by one.
          </p>
          <p className={styles.uploadSupport}>
            Supported: {KB_UPLOAD_ALLOWED_EXTENSIONS.join(" ")}
          </p>

          {contentUploadError && (
            <AlertBanner message={contentUploadError} variant="error" className={styles.uploadAlert} />
          )}
          {contentUploadNotice && (
            <AlertBanner message={contentUploadNotice} variant="success" className={styles.uploadAlert} />
          )}

          {loadingContentSchema ? (
            <LoadingState className="h-24" size="default" />
          ) : contentUploadSchema ? (
            <div className={styles.uploadForm}>
              <SchemaForm
                key={contentFormKey}
                schema={contentUploadSchema}
                onSubmit={handleContentUpload}
                submitLabel="Upload Files"
                isLoading={isUploadingContent}
              />
            </div>
          ) : (
            <InlineEmptyState
              icon={Database}
              title="Upload form unavailable"
              description="We couldn't load the upload form. Please refresh the page."
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-[var(--gradient-start)]" />
              <CardTitle className="text-lg">Recent Uploads</CardTitle>
            </div>
            {hasMoreUploads && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => loadUploads({ cursor: uploadsCursor })}
                disabled={loadingUploads}
              >
                {loadingUploads ? "Loading..." : "Load More"}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {uploadsError && (
            <AlertBanner message={uploadsError} variant="error" className="mb-4" />
          )}
          {loadingUploads && uploads.length === 0 ? (
            <LoadingState className="h-24" size="default" />
          ) : uploads.length === 0 ? (
            <InlineEmptyState
              icon={FileText}
              title="No uploads yet"
              description="Upload a file to start building your knowledge base"
            />
          ) : (
            <div className={styles.uploadsList}>
              {uploads.map((upload) => (
                <div
                  key={upload.upload_id}
                  className={styles.uploadItem}
                >
                  <div className={styles.uploadRow}>
                    <div className={styles.uploadInfo}>
                      <div className={styles.uploadIcon}>
                        <FileText className="h-4 w-4 text-[var(--text-muted)]" />
                      </div>
                      <div>
                        <p className={styles.uploadTitle}>
                          {upload.filename}
                        </p>
                        <p className={styles.uploadMeta}>
                          {formatFileSize(upload.size_bytes)} • {formatDate(upload.created_at)}
                        </p>
                        {upload.metadata && (
                          <p className={styles.uploadMetadata}>
                            {upload.metadata}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className={styles.uploadStats}>
                      <div>{upload.chunk_count} chunks</div>
                      <div>{upload.vector_count} vectors</div>
                    </div>
                  </div>
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
