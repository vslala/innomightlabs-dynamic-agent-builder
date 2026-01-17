/**
 * Conversation API Service - calls backend REST API for conversation CRUD operations.
 */

import { httpClient } from "../http/client";
import type {
  ConversationResponse,
  CreateConversationRequest,
  UpdateConversationRequest,
  PaginatedResponse,
} from "../../types/conversation";

class ConversationApiService {
  /**
   * List all conversations for the current user with pagination.
   */
  async listConversations(
    limit: number = 10,
    cursor?: string
  ): Promise<PaginatedResponse<ConversationResponse>> {
    const params = new URLSearchParams();
    params.append("limit", limit.toString());
    if (cursor) {
      params.append("cursor", cursor);
    }
    return httpClient.get<PaginatedResponse<ConversationResponse>>(
      `/conversations/?${params.toString()}`
    );
  }

  /**
   * Get a single conversation by ID.
   */
  async getConversation(conversationId: string): Promise<ConversationResponse> {
    return httpClient.get<ConversationResponse>(
      `/conversations/${conversationId}`
    );
  }

  /**
   * Create a new conversation.
   */
  async createConversation(
    data: CreateConversationRequest
  ): Promise<ConversationResponse> {
    return httpClient.post<ConversationResponse>("/conversations/", data);
  }

  /**
   * Update an existing conversation.
   */
  async updateConversation(
    conversationId: string,
    data: UpdateConversationRequest
  ): Promise<ConversationResponse> {
    return httpClient.put<ConversationResponse>(
      `/conversations/${conversationId}`,
      data
    );
  }

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId: string): Promise<void> {
    await httpClient.delete(`/conversations/${conversationId}`);
  }
}

// Singleton instance
export const conversationApiService = new ConversationApiService();
