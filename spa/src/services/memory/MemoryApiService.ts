/**
 * Memory Blocks API Service - calls backend REST API for memory block operations.
 */

import { httpClient } from "../http/client";

// Memory block metadata response
export interface MemoryBlockResponse {
  block_name: string;
  description: string;
  word_limit: number;
  is_default: boolean;
  word_count: number;
  capacity_percent: number;
  created_at: string;
}

// Memory block content response
export interface MemoryBlockContentResponse {
  block_name: string;
  lines: string[];
  word_count: number;
  word_limit: number;
  capacity_percent: number;
  is_default: boolean;
}

// Request to create a new memory block
export interface CreateMemoryBlockRequest {
  name: string;
  description: string;
  word_limit?: number;
}

// Request to update memory block content
export interface UpdateMemoryBlockContentRequest {
  lines: string[];
}

class MemoryApiService {
  /**
   * List all memory blocks for an agent
   */
  async listMemoryBlocks(agentId: string): Promise<MemoryBlockResponse[]> {
    return httpClient.get<MemoryBlockResponse[]>(
      `/agents/${agentId}/memory-blocks`
    );
  }

  /**
   * Create a new custom memory block
   */
  async createMemoryBlock(
    agentId: string,
    data: CreateMemoryBlockRequest
  ): Promise<MemoryBlockResponse> {
    return httpClient.post<MemoryBlockResponse>(
      `/agents/${agentId}/memory-blocks`,
      data
    );
  }

  /**
   * Delete a custom memory block
   */
  async deleteMemoryBlock(agentId: string, blockName: string): Promise<void> {
    await httpClient.delete(`/agents/${agentId}/memory-blocks/${blockName}`);
  }

  /**
   * Get the content (lines) of a memory block
   */
  async getMemoryBlockContent(
    agentId: string,
    blockName: string
  ): Promise<MemoryBlockContentResponse> {
    return httpClient.get<MemoryBlockContentResponse>(
      `/agents/${agentId}/memory-blocks/${blockName}/content`
    );
  }

  /**
   * Update the content of a custom memory block
   */
  async updateMemoryBlockContent(
    agentId: string,
    blockName: string,
    data: UpdateMemoryBlockContentRequest
  ): Promise<MemoryBlockContentResponse> {
    return httpClient.put<MemoryBlockContentResponse>(
      `/agents/${agentId}/memory-blocks/${blockName}/content`,
      data
    );
  }
}

// Singleton instance
export const memoryApiService = new MemoryApiService();
