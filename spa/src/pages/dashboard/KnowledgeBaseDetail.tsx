import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Database,
  ChevronLeft,
  Pencil,
  Plus,
  Play,
  RotateCcw,
  XCircle,
  Globe,
  Loader2,
  FileText,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  SectionCardHeader,
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
  ExpandableCard,
  ListRow,
} from "../../components/ui";
import { Page, PageHeader, PageActions, PageBody, Stack, Inline, FieldGroup } from "../../components/layout";
import { SchemaForm } from "../../components/forms";
import styles from "./KnowledgeBaseDetail.module.css";
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

  const handleRunOrRetryJob = async (jobId: string) => {
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
        const response = lastResponse;
        if (response) {
          setKb((prev) =>
            prev
              ? {
                ...prev,
                total_pages: response.total_pages,
                total_chunks: response.total_chunks,
                total_vectors: response.total_vectors,
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
      <Page>
        <PageHeader>
          <Inline gap="sm">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate("/dashboard/knowledge-bases")}
            >
              <ChevronLeft className="h-5 w-5" />
            </Button>
            <h1 className={styles.pageTitle}>
              Knowledge Base Not Found
            </h1>
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
    <Page style={{ maxWidth: "48rem" }}>
      <PageHeader>
        <Inline gap="sm">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/dashboard/knowledge-bases")}
          >
            <ChevronLeft className="h-5 w-5" />
          </Button>
          <div className={styles.pageIconBox}>
            <Database className={styles.pageIcon} />
          </div>
          <div>
            <h1 className={styles.pageTitle}>
              {kb.name}
            </h1>
            <p className={styles.pageSubtitle}>
              {kb.total_pages} pages • {kb.total_chunks} chunks
            </p>
          </div>
        </Inline>
        {!isEditing && (
          <PageActions>
            <Button variant="outline" onClick={() => setIsEditing(true)}>
              <Pencil className="h-4 w-4" />
              Edit
            </Button>
          </PageActions>
        )}
      </PageHeader>

      <PageBody>
      <Card>
        <CardHeader>
          <CardTitle className={styles.detailsCardTitle}>
            {isEditing ? "Edit Knowledge Base" : "Details"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Stack gap="md">
            {error && <AlertBanner message={error} variant="error" />}

            {isEditing ? (
              <Stack gap="md">
                <FieldGroup>
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </FieldGroup>
                <FieldGroup>
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={3}
                  />
                </FieldGroup>
                <Inline gap="xs" justify="flex-end">
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
                </Inline>
              </Stack>
            ) : (
              <Stack gap="md">
                <div>
                  <Label className={styles.detailsLabel}>Description</Label>
                  <p className={styles.detailsDescription}>
                    {kb.description || "No description"}
                  </p>
                </div>

                <div className={styles.statsSection}>
                  <StatsGrid columns={3}>
                    <StatItem label="Pages" value={kb.total_pages.toLocaleString()} />
                    <StatItem label="Chunks" value={kb.total_chunks.toLocaleString()} />
                    <StatItem label="Vectors" value={kb.total_vectors.toLocaleString()} />
                  </StatsGrid>
                </div>

                <div className={styles.createdRow}>
                  Created {formatDate(kb.created_at)}
                </div>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionCardHeader
            icon={Globe}
            title="Web Crawl Jobs"
            status={isPolling && (
              <Loader2 className={styles.pollingSpinner} />
            )}
            action={
              <Button size="sm" onClick={() => setIsStartCrawlDialogOpen(true)}>
                <Plus className="h-4 w-4" />
                Start Crawl
              </Button>
            }
          />
        </CardHeader>
        <CardContent>
          {loadingJobs ? (
            <LoadingState className={styles.jobsLoadingState} size="default" />
          ) : crawlJobs.length === 0 ? (
            <InlineEmptyState
              icon={Globe}
              title="No crawl jobs yet"
              description="Start a crawl to import content from a website"
            />
          ) : (
            <Stack gap="md">
              {crawlJobs.map((job) => (
                <ExpandableCard
                  key={job.job_id}
                  expanded={expandedJobId === job.job_id}
                  onToggle={() =>
                    setExpandedJobId(expandedJobId === job.job_id ? null : job.job_id)
                  }
                  header={
                    <Inline justify="space-between" wrap={false}>
                      <Inline gap="sm" wrap={false}>
                        <StatusIcon status={mapStatus(job.status)} />
                        <div className={styles.jobTitleWrap}>
                          <p className={styles.jobUrl}>
                            {job.config.source_url}
                          </p>
                          <p className={styles.jobMeta}>
                            {job.config.source_type} • {formatDate(job.created_at)}
                          </p>
                        </div>
                      </Inline>
                      <Inline gap="sm" wrap={false}>
                        {job.status === "in_progress" && (
                          <span className={styles.progressPercent}>
                            {getProgressPercentage(job)}%
                          </span>
                        )}
                        <StatusBadge status={mapStatus(job.status)} />
                        {job.status === "in_progress" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className={styles.cancelButton}
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
                            className={styles.runRetryButton}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRunOrRetryJob(job.job_id);
                            }}
                          >
                            <Play className="h-4 w-4" />
                          </Button>
                        )}
                        {job.status === "failed" && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className={styles.runRetryButton}
                            title={
                              job.checkpoint && job.checkpoint.pending_urls.length > 0
                                ? `Retry (resumes from page ${job.checkpoint.current_url_index} of ${job.checkpoint.pending_urls.length})`
                                : "Retry"
                            }
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRunOrRetryJob(job.job_id);
                            }}
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                        )}
                      </Inline>
                    </Inline>
                  }
                >
                  <Stack gap="md">
                    {/* Progress bar for in-progress and completed jobs */}
                    {(job.status === "in_progress" || job.status === "completed") && (
                      <div>
                        <div className={styles.progressHeader}>
                          <span className={styles.progressLabel}>
                            {job.status === "in_progress" ? "Crawling..." : "Completed"}
                          </span>
                          <span className={styles.progressCount}>
                            {job.progress.processed_urls} / {job.progress.discovered_urls} pages
                          </span>
                        </div>
                        <ProgressBar
                          value={job.progress.processed_urls}
                          max={job.progress.discovered_urls || 1}
                        />
                      </div>
                    )}

                    <Stack gap="sm">
                      <StatsGrid columns={4}>
                        <StatItem label="Discovered" value={job.progress.discovered_urls} />
                        <StatItem label="Processed" value={job.progress.processed_urls} />
                        <StatItem label="Success" value={job.progress.successful_urls} valueClassName={styles.successStatValue} />
                        <StatItem label="Failed" value={job.progress.failed_urls} valueClassName={styles.failedStatValue} />
                      </StatsGrid>

                      <StatsGrid columns={4}>
                        <StatItem label="Chunks" value={job.progress.total_chunks} />
                        <StatItem label="Embeddings" value={job.progress.total_embeddings} />
                        <StatItem label="Duration" value={formatDuration(job.timing.total_duration_ms)} />
                        <StatItem label="Avg/Page" value={formatDuration(job.timing.avg_page_duration_ms)} />
                      </StatsGrid>
                    </Stack>

                    {/* Error message */}
                    {job.error_message && (
                      <AlertBanner message={job.error_message} variant="error" />
                    )}

                    {/* Resume hint for failed jobs with a saved checkpoint */}
                    {job.status === "failed" &&
                      job.checkpoint &&
                      job.checkpoint.pending_urls.length > 0 && (
                        <p className={styles.resumeHint}>
                          Retrying will resume from page {job.checkpoint.current_url_index} of{" "}
                          {job.checkpoint.pending_urls.length} instead of starting over.
                        </p>
                      )}

                    {/* Configuration */}
                    <div className={styles.configSection}>
                      <p className={styles.configLabel}>
                        Configuration
                      </p>
                      <PillGroup>
                        <Pill variant="outline">Max Pages: {job.config.max_pages}</Pill>
                        <Pill variant="outline">Max Depth: {job.config.max_depth}</Pill>
                        <Pill variant="outline">Rate Limit: {job.config.rate_limit_ms}ms</Pill>
                      </PillGroup>
                    </div>
                  </Stack>
                </ExpandableCard>
              ))}
            </Stack>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionCardHeader icon={Database} title="Upload Content" />
        </CardHeader>
        <CardContent>
          <Stack gap="md">
            <p className={styles.uploadHint}>
              Upload text-based files (max 5MB per file). Multiple files will upload one by one.
            </p>
            <p className={styles.uploadSupportedTypes}>
              Supported: {KB_UPLOAD_ALLOWED_EXTENSIONS.join(" ")}
            </p>

            {contentUploadError && (
              <AlertBanner message={contentUploadError} variant="error" />
            )}
            {contentUploadNotice && (
              <AlertBanner message={contentUploadNotice} variant="success" />
            )}

            {loadingContentSchema ? (
              <LoadingState className={styles.uploadFormLoadingState} size="default" />
            ) : contentUploadSchema ? (
              <SchemaForm
                key={contentFormKey}
                schema={contentUploadSchema}
                onSubmit={handleContentUpload}
                submitLabel="Upload Files"
                isLoading={isUploadingContent}
              />
            ) : (
              <InlineEmptyState
                icon={Database}
                title="Upload form unavailable"
                description="We couldn't load the upload form. Please refresh the page."
              />
            )}
          </Stack>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionCardHeader
            icon={FileText}
            title="Recent Uploads"
            action={
              hasMoreUploads && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => loadUploads({ cursor: uploadsCursor })}
                  disabled={loadingUploads}
                >
                  {loadingUploads ? "Loading..." : "Load More"}
                </Button>
              )
            }
          />
        </CardHeader>
        <CardContent>
          <Stack gap="md">
            {uploadsError && <AlertBanner message={uploadsError} variant="error" />}
            {loadingUploads && uploads.length === 0 ? (
              <LoadingState className={styles.uploadsLoadingState} size="default" />
            ) : uploads.length === 0 ? (
              <InlineEmptyState
                icon={FileText}
                title="No uploads yet"
                description="Upload a file to start building your knowledge base"
              />
            ) : (
              uploads.map((upload) => (
                <ListRow
                  key={upload.upload_id}
                  icon={<FileText className={styles.uploadRowIcon} />}
                  title={upload.filename}
                  subtitle={`${formatFileSize(upload.size_bytes)} • ${formatDate(upload.created_at)}`}
                  meta={upload.metadata || undefined}
                  trailing={
                    <>
                      <div>{upload.chunk_count} chunks</div>
                      <div>{upload.vector_count} vectors</div>
                    </>
                  }
                />
              ))
            )}
          </Stack>
        </CardContent>
      </Card>
      </PageBody>

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

          {crawlError && <AlertBanner message={crawlError} variant="error" />}

          <Stack gap="md" className={styles.crawlFormFields}>
            <FieldGroup>
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
              <p className={styles.sourceTypeHint}>
                {crawlSourceType === "sitemap"
                  ? "Provide a sitemap.xml URL to crawl all listed pages"
                  : "Provide a starting URL to crawl and follow links"}
              </p>
            </FieldGroup>

            <FieldGroup>
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
            </FieldGroup>

            <div className={styles.crawlNumbersGrid}>
              <FieldGroup>
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
              </FieldGroup>
              <FieldGroup>
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
                <p className={styles.maxDepthHint}>Only for URL crawling</p>
              </FieldGroup>
            </div>
          </Stack>
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
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Start Crawl
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
