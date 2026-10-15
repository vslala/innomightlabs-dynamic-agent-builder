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
import type { Message } from "../../types/message";
import type { UploadedLeadFile } from "../../types/leads";
import type { UploadedImage } from "../../../packages/image-attachments/src";

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

  /**
   * Upload an image to send with the conversation's next message. The API checks it (type, size, that the
   * account allows images) and refuses with a message fit to show.
   */
  async uploadImage(conversationId: string, file: File): Promise<UploadedImage> {
    const form = new FormData();
    form.append("file", file);
    return httpClient.postForm<UploadedImage>(`/conversations/${conversationId}/images`, form);
  }

  /** Upload a file into a lead form's field while trying the form in chat; its id becomes the field's answer. */
  async uploadLeadFile(conversationId: string, leadForm: string, inputName: string, file: File): Promise<UploadedLeadFile> {
    const form = new FormData();
    form.append("form", leadForm);
    form.append("input", inputName);
    form.append("file", file);
    return httpClient.postForm<UploadedLeadFile>(`/conversations/${conversationId}/lead-files`, form);
  }

  /**
   * Get messages for a conversation with pagination.
   * Returns messages newest-first. Use cursor to load older messages.
   */
  async getMessages(
    conversationId: string,
    limit: number = 20,
    cursor?: string
  ): Promise<PaginatedResponse<Message>> {
    const params = new URLSearchParams();
    params.append("limit", limit.toString());
    if (cursor) {
      params.append("cursor", cursor);
    }
    return httpClient.get<PaginatedResponse<Message>>(
      `/conversations/${conversationId}/messages?${params.toString()}`
    );
  }
}

// Singleton instance
export const conversationApiService = new ConversationApiService();
