/**
 * Widget configuration options passed to InnomightChat.init()
 */
export interface WidgetConfig {
  /** Public API key (pk_live_xxx) */
  apiKey: string;
  /** API base URL (defaults to production) */
  apiUrl?: string;
  /** Widget position on screen */
  position?: 'bottom-right' | 'bottom-left';
  /** Color theme */
  theme?: 'light' | 'dark';
  /** Primary color (hex) */
  primaryColor?: string;
  /** Initial greeting message */
  greeting?: string;
  /** Placeholder text for input */
  placeholder?: string;
}

/**
 * Visitor information from OAuth
 */
export interface Visitor {
  visitorId: string;
  email: string;
  name?: string;
  picture?: string;
}

/**
 * Conversation metadata
 */
export interface Conversation {
  conversationId: string;
  agentId: string;
  visitorId: string;
  visitorName?: string;
  title: string;
  createdAt: string;
  updatedAt?: string;
  messageCount: number;
}

/**
 * Chat message
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

/**
 * SSE event types from the API
 */
export type SSEEventType =
  | 'LIFECYCLE_NOTIFICATION'
  | 'AGENT_RESPONSE_TO_USER'
  | 'MESSAGE_SAVED'
  | 'STREAM_COMPLETE'
  | 'ERROR';

/**
 * SSE event payload
 */
export interface SSEEvent {
  event_type: SSEEventType;
  content: string;
  metadata?: Record<string, unknown>;
}

/**
 * Widget state
 */
export interface WidgetState {
  isOpen: boolean;
  isAuthenticated: boolean;
  isLoading: boolean;
  visitor: Visitor | null;
  conversations: Conversation[];
  currentConversation: Conversation | null;
  messages: Message[];
  error: string | null;
}

/**
 * Storage keys for localStorage
 */
export const STORAGE_KEYS = {
  VISITOR_TOKEN: 'innomight_visitor_token',
  VISITOR_INFO: 'innomight_visitor_info',
  CURRENT_CONVERSATION: 'innomight_current_conversation',
} as const;
