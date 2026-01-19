/**
 * Knowledge Base types - aligned with backend models
 */

// =============================================================================
// Enums
// =============================================================================

export type KnowledgeBaseStatus = "active" | "deleted";

export type CrawlJobStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled";

export type CrawlSourceType = "sitemap" | "url";

export type CrawlStepType =
  | "JOB_STARTED"
  | "JOB_COMPLETED"
  | "JOB_FAILED"
  | "JOB_CHECKPOINT"
  | "URL_DISCOVERED"
  | "URL_SKIPPED"
  | "PAGE_FETCH_START"
  | "PAGE_FETCH_COMPLETE"
  | "PAGE_FETCH_ERROR"
  | "PAGE_PARSE_START"
  | "PAGE_PARSE_COMPLETE"
  | "PAGE_CHUNK_START"
  | "PAGE_CHUNK_COMPLETE"
  | "PAGE_EMBED_START"
  | "PAGE_EMBED_COMPLETE"
  | "PAGE_INGEST_START"
  | "PAGE_INGEST_COMPLETE";

export type CrawledPageStatus = "pending" | "success" | "failed" | "skipped";

// =============================================================================
// Knowledge Base
// =============================================================================

export interface KnowledgeBase {
  kb_id: string;
  name: string;
  description: string;
  pinecone_namespace: string;
  total_pages: number;
  total_chunks: number;
  total_vectors: number;
  status: KnowledgeBaseStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CreateKnowledgeBaseInput {
  name: string;
  description?: string;
}

export interface UpdateKnowledgeBaseInput {
  name?: string;
  description?: string;
}

// =============================================================================
// Crawl Job
// =============================================================================

export interface CrawlConfig {
  source_type: CrawlSourceType;
  source_url: string;
  max_pages: number;
  max_depth: number;
  rate_limit_ms: number;
  respect_robots_txt: boolean;
  chunking_strategy: string;
}

export interface CrawlProgress {
  discovered_urls: number;
  processed_urls: number;
  successful_urls: number;
  failed_urls: number;
  total_chunks: number;
  total_embeddings: number;
}

export interface CrawlTiming {
  started_at: string | null;
  completed_at: string | null;
  total_duration_ms: number | null;
  avg_page_duration_ms: number | null;
}

export interface CrawlJob {
  job_id: string;
  kb_id: string;
  status: CrawlJobStatus;
  config: CrawlConfig;
  progress: CrawlProgress;
  timing: CrawlTiming;
  error_message: string | null;
  created_by: string;
  created_at: string;
}

export interface StartCrawlJobInput {
  source_type: CrawlSourceType;
  source_url: string;
  max_pages?: number;
  max_depth?: number;
  rate_limit_ms?: number;
  chunking_strategy?: string;
}

// =============================================================================
// Crawl Step (Audit Log)
// =============================================================================

export interface CrawlStep {
  step_id: string;
  job_id: string;
  step_type: CrawlStepType;
  url: string | null;
  details: Record<string, unknown>;
  duration_ms: number | null;
  timestamp: string;
}

// =============================================================================
// Crawled Page
// =============================================================================

export interface PageMetadata {
  title: string;
  description: string;
  content_length: number;
  word_count: number;
}

export interface PageTiming {
  fetch_duration_ms: number | null;
  parse_duration_ms: number | null;
  chunk_duration_ms: number | null;
  embed_duration_ms: number | null;
  ingest_duration_ms: number | null;
  total_duration_ms: number | null;
}

export interface CrawledPage {
  job_id: string;
  url: string;
  url_hash: string;
  status: CrawledPageStatus;
  page_metadata: PageMetadata | null;
  chunk_count: number;
  timing: PageTiming | null;
  error: string | null;
  crawled_at: string | null;
}

// =============================================================================
// Search
// =============================================================================

export interface SearchResult {
  chunk_id: string;
  content: string;
  source_url: string;
  page_title: string;
  score: number;
}

export interface SearchResponse {
  results: SearchResult[];
  query: string;
}

// =============================================================================
// SSE Events
// =============================================================================

export type CrawlEventType =
  | "JOB_STARTED"
  | "JOB_PROGRESS"
  | "JOB_CHECKPOINT"
  | "JOB_COMPLETED"
  | "JOB_FAILED"
  | "URL_DISCOVERED"
  | "URL_SKIPPED"
  | "PAGE_FETCH_START"
  | "PAGE_FETCH_COMPLETE"
  | "PAGE_FETCH_ERROR"
  | "PAGE_PARSE_START"
  | "PAGE_PARSE_COMPLETE"
  | "PAGE_CHUNK_START"
  | "PAGE_CHUNK_COMPLETE"
  | "PAGE_EMBED_START"
  | "PAGE_EMBED_COMPLETE"
  | "PAGE_INGEST_START"
  | "PAGE_INGEST_COMPLETE"
  | "PAGE_ERROR";

export interface CrawlEvent {
  event_type: CrawlEventType;
  step_id?: string;
  job_id: string;
  kb_id: string;
  timestamp: string;
  url?: string;
  status?: CrawlJobStatus;
  progress?: CrawlProgress;
  error_message?: string;
  details?: Record<string, unknown>;
  duration_ms?: number;
  cursor?: string;
}
