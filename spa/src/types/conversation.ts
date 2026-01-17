/**
 * Conversation types matching backend API.
 */

export interface ConversationResponse {
  conversation_id: string;
  title: string;
  description: string | null;
  agent_id: string;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface CreateConversationRequest {
  title: string;
  description?: string;
  agent_id: string;
}

export interface UpdateConversationRequest {
  title?: string;
  description?: string;
  agent_id?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
}
