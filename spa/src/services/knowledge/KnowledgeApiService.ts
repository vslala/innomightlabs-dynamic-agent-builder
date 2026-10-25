/**
 * Knowledge Base API Service
 *
 * Handles all API communication for Knowledge Base features including:
 * - Knowledge Base CRUD
 * - Documents (uploaded files, read and indexed in the background)
 * - Crawl Job management
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
  KnowledgePage,
  KnowledgePageCounts,
  KnowledgePageDetail,
  KnowledgePageState,
  SearchResponse,
  KnowledgeDocument,
  PaginatedResponse,
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
   * Get the form schema for content uploads
   */
  async getContentUploadSchema(kbId: string): Promise<FormSchema> {
    return httpClient.get<FormSchema>(
      `/knowledge-bases/${kbId}/forms/content-upload`
    );
  }

  /**
   * Upload one file to a knowledge base. The API accepts it (202) as a pending document and reads and indexes it
   * in the background; poll the document (or the list) for its status.
   */
  async uploadContentFile(
    kbId: string,
    payload: { metadata?: string; file: File }
  ): Promise<KnowledgeDocument> {
    const formData = new FormData();
    formData.append("attachment", payload.file);
    if (payload.metadata) {
      formData.append("metadata", payload.metadata);
    }
    return httpClient.postForm<KnowledgeDocument>(
      `/knowledge-bases/${kbId}/content-upload`,
      formData
    );
  }

  /**
   * A page of the knowledge base's documents, newest first
   */
  async listDocuments(
    kbId: string,
    limit = 10,
    cursor?: string | null
  ): Promise<PaginatedResponse<KnowledgeDocument>> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return httpClient.get<PaginatedResponse<KnowledgeDocument>>(`/knowledge-bases/${kbId}/documents?${params}`);
  }

  async getDocument(kbId: string, documentId: string): Promise<KnowledgeDocument> {
    return httpClient.get<KnowledgeDocument>(`/knowledge-bases/${kbId}/documents/${documentId}`);
  }

  /**
   * Read a failed document again from the stored file (409 unless it failed)
   */
  async retryDocument(kbId: string, documentId: string): Promise<KnowledgeDocument> {
    return httpClient.post<KnowledgeDocument>(`/knowledge-bases/${kbId}/documents/${documentId}/retry`);
  }

  /**
   * Delete a document and its page from the index (503 means try again)
   */
  async deleteDocument(kbId: string, documentId: string): Promise<void> {
    await httpClient.delete(`/knowledge-bases/${kbId}/documents/${documentId}`);
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
   * A page of a knowledge base's crawl jobs, newest first
   */
  async listCrawlJobs(
    kbId: string,
    limit = 5,
    cursor?: string | null
  ): Promise<PaginatedResponse<CrawlJob>> {
    const cursorParam = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
    return httpClient.get<PaginatedResponse<CrawlJob>>(
      `/knowledge-bases/${kbId}/crawl-jobs?limit=${limit}${cursorParam}`
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

  /**
   * A page of the knowledge base's pages as they are now, those that need a look first
   */
  async listPages(
    kbId: string,
    filter: { state?: KnowledgePageState; search?: string; limit?: number; cursor?: string | null } = {}
  ): Promise<PaginatedResponse<KnowledgePage>> {
    const params = new URLSearchParams({ limit: String(filter.limit ?? 25) });
    if (filter.state) params.set("state", filter.state);
    if (filter.search) params.set("search", filter.search);
    if (filter.cursor) params.set("cursor", filter.cursor);
    return httpClient.get<PaginatedResponse<KnowledgePage>>(`/knowledge-bases/${kbId}/pages?${params}`);
  }

  /**
   * One page with its chunks
   */
  async getPage(kbId: string, url: string): Promise<KnowledgePageDetail> {
    return httpClient.get<KnowledgePageDetail>(`/knowledge-bases/${kbId}/pages/detail?url=${encodeURIComponent(url)}`);
  }

  /**
   * How many pages the knowledge base has in each state
   */
  async countPages(kbId: string): Promise<KnowledgePageCounts> {
    return httpClient.get<KnowledgePageCounts>(`/knowledge-bases/${kbId}/pages/counts`);
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

  // ===========================================================================
  // Agent Knowledge Base Links
  // ===========================================================================

  /**
   * Link a knowledge base to an agent
   */
  async linkKnowledgeBaseToAgent(
    agentId: string,
    kbId: string
  ): Promise<{ message: string; kb_id: string; agent_id: string; linked_at: string }> {
    return httpClient.post(`/agents/${agentId}/knowledge-bases?kb_id=${kbId}`);
  }

  /**
   * List knowledge bases linked to an agent
   */
  async listAgentKnowledgeBases(agentId: string): Promise<KnowledgeBase[]> {
    return httpClient.get<KnowledgeBase[]>(`/agents/${agentId}/knowledge-bases`);
  }

  /**
   * Unlink a knowledge base from an agent
   */
  async unlinkKnowledgeBaseFromAgent(
    agentId: string,
    kbId: string
  ): Promise<void> {
    return httpClient.delete(`/agents/${agentId}/knowledge-bases/${kbId}`);
  }

  /**
   * Search across all knowledge bases linked to an agent
   */
  async searchAgentKnowledgeBases(
    agentId: string,
    query: string,
    topK = 5
  ): Promise<SearchResponse> {
    return httpClient.post<SearchResponse>(
      `/agents/${agentId}/knowledge-search?query=${encodeURIComponent(query)}&top_k=${topK}`
    );
  }
}

export const knowledgeApiService = new KnowledgeApiService();
