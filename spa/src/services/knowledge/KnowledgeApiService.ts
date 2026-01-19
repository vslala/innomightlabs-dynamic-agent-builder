/**
 * Knowledge Base API Service
 *
 * Handles all API communication for Knowledge Base features including:
 * - Knowledge Base CRUD
 * - Crawl Job management
 * - Crawl progress streaming (SSE)
 * - Search
 */

import { httpClient } from "../http/client";
import type { FormSchema } from "../../types/form";
import type {
  KnowledgeBase,
  CreateKnowledgeBaseInput,
  UpdateKnowledgeBaseInput,
  CrawlJob,
  StartCrawlJobInput,
  CrawlStep,
  CrawledPage,
  SearchResponse,
  CrawlEvent,
} from "../../types/knowledge";

class KnowledgeApiService {
  // ===========================================================================
  // Knowledge Base CRUD
  // ===========================================================================

  /**
   * Get the form schema for creating a knowledge base
   */
  async getCreateSchema(): Promise<FormSchema> {
    return httpClient.get<FormSchema>("/knowledge-bases/create-schema");
  }

  /**
   * List all knowledge bases for the current user
   */
  async listKnowledgeBases(): Promise<KnowledgeBase[]> {
    return httpClient.get<KnowledgeBase[]>("/knowledge-bases");
  }

  /**
   * Get a knowledge base by ID
   */
  async getKnowledgeBase(kbId: string): Promise<KnowledgeBase> {
    return httpClient.get<KnowledgeBase>(`/knowledge-bases/${kbId}`);
  }

  /**
   * Create a new knowledge base
   */
  async createKnowledgeBase(
    input: CreateKnowledgeBaseInput
  ): Promise<KnowledgeBase> {
    return httpClient.post<KnowledgeBase>("/knowledge-bases", input);
  }

  /**
   * Update a knowledge base
   */
  async updateKnowledgeBase(
    kbId: string,
    input: UpdateKnowledgeBaseInput
  ): Promise<KnowledgeBase> {
    return httpClient.patch<KnowledgeBase>(`/knowledge-bases/${kbId}`, input);
  }

  /**
   * Delete a knowledge base (soft delete)
   */
  async deleteKnowledgeBase(kbId: string): Promise<void> {
    return httpClient.delete(`/knowledge-bases/${kbId}`);
  }

  // ===========================================================================
  // Crawl Jobs
  // ===========================================================================

  /**
   * Get the form schema for configuring a crawl job
   */
  async getCrawlConfigSchema(kbId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(
      `/knowledge-bases/${kbId}/crawl-config-schema`
    );
  }

  /**
   * Start a new crawl job
   * @param kbId Knowledge base ID
   * @param input Crawl configuration
   * @param autoStart Whether to start crawling immediately (default: true)
   */
  async startCrawlJob(
    kbId: string,
    input: StartCrawlJobInput,
    autoStart = true
  ): Promise<CrawlJob> {
    return httpClient.post<CrawlJob>(
      `/knowledge-bases/${kbId}/crawl-jobs?auto_start=${autoStart}`,
      input
    );
  }

  /**
   * List crawl jobs for a knowledge base
   */
  async listCrawlJobs(kbId: string, limit = 5): Promise<CrawlJob[]> {
    return httpClient.get<CrawlJob[]>(
      `/knowledge-bases/${kbId}/crawl-jobs?limit=${limit}`
    );
  }

  /**
   * Get a crawl job by ID
   */
  async getCrawlJob(kbId: string, jobId: string): Promise<CrawlJob> {
    return httpClient.get<CrawlJob>(
      `/knowledge-bases/${kbId}/crawl-jobs/${jobId}`
    );
  }

  /**
   * Manually run a pending crawl job
   */
  async runCrawlJob(kbId: string, jobId: string): Promise<CrawlJob> {
    return httpClient.post<CrawlJob>(
      `/knowledge-bases/${kbId}/crawl-jobs/${jobId}/run`
    );
  }

  /**
   * Cancel a crawl job
   */
  async cancelCrawlJob(kbId: string, jobId: string): Promise<void> {
    return httpClient.delete(`/knowledge-bases/${kbId}/crawl-jobs/${jobId}`);
  }

  /**
   * Get audit log steps for a crawl job
   */
  async getCrawlSteps(
    kbId: string,
    jobId: string,
    limit = 100
  ): Promise<CrawlStep[]> {
    return httpClient.get<CrawlStep[]>(
      `/knowledge-bases/${kbId}/crawl-jobs/${jobId}/steps?limit=${limit}`
    );
  }

  /**
   * Get crawled pages for a crawl job
   */
  async getCrawledPages(
    kbId: string,
    jobId: string,
    limit = 100
  ): Promise<CrawledPage[]> {
    return httpClient.get<CrawledPage[]>(
      `/knowledge-bases/${kbId}/crawl-jobs/${jobId}/pages?limit=${limit}`
    );
  }

  // ===========================================================================
  // SSE Streaming
  // ===========================================================================

  /**
   * Stream crawl job progress updates via SSE (polls database)
   * @param cursor Optional cursor for resuming from last seen step
   * @returns EventSource that emits CrawlEvent objects
   */
  streamCrawlProgress(
    kbId: string,
    jobId: string,
    onEvent: (event: CrawlEvent) => void,
    onError?: (error: Event) => void,
    cursor?: string
  ): EventSource {
    const baseUrl =
      import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
    const token = localStorage.getItem("auth_token");

    const params = new URLSearchParams();
    if (token) params.set("token", token);
    if (cursor) params.set("cursor", cursor);

    const queryString = params.toString();
    const url = `${baseUrl}/knowledge-bases/${kbId}/crawl-jobs/${jobId}/stream${
      queryString ? `?${queryString}` : ""
    }`;

    const eventSource = new EventSource(url);

    const eventTypes = [
      "connected",
      "JOB_STARTED",
      "JOB_PROGRESS",
      "JOB_CHECKPOINT",
      "JOB_COMPLETED",
      "JOB_FAILED",
      "URL_DISCOVERED",
      "URL_SKIPPED",
      "PAGE_FETCH_START",
      "PAGE_FETCH_COMPLETE",
      "PAGE_FETCH_ERROR",
      "PAGE_PARSE_START",
      "PAGE_PARSE_COMPLETE",
      "PAGE_CHUNK_START",
      "PAGE_CHUNK_COMPLETE",
      "PAGE_EMBED_START",
      "PAGE_EMBED_COMPLETE",
      "PAGE_INGEST_START",
      "PAGE_INGEST_COMPLETE",
      "PAGE_ERROR",
    ];

    eventTypes.forEach((eventType) => {
      eventSource.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as CrawlEvent;
          onEvent(data);
        } catch (err) {
          console.error("Failed to parse SSE event:", err);
        }
      });
    });

    eventSource.onerror = (e) => {
      if (onError) {
        onError(e);
      }
    };

    return eventSource;
  }

  // ===========================================================================
  // Search
  // ===========================================================================

  /**
   * Search a knowledge base for relevant content
   */
  async searchKnowledgeBase(
    kbId: string,
    query: string,
    topK = 5
  ): Promise<SearchResponse> {
    return httpClient.post<SearchResponse>(
      `/knowledge-bases/${kbId}/search?query=${encodeURIComponent(query)}&top_k=${topK}`
    );
  }
}

export const knowledgeApiService = new KnowledgeApiService();
