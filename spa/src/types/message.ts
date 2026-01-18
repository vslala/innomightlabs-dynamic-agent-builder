/**
 * Message types matching backend API.
 */

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  created_at: string;
}

/**
 * SSE Event types matching backend enum.
 */
export const SSEEventType = {
  LIFECYCLE_NOTIFICATION: "LIFECYCLE_NOTIFICATION",
  AGENT_RESPONSE_TO_USER: "AGENT_RESPONSE_TO_USER",
  AGENT_THOUGHTS: "AGENT_THOUGHTS",
  MESSAGE_SAVED: "MESSAGE_SAVED",
  STREAM_COMPLETE: "STREAM_COMPLETE",
  ERROR: "ERROR",
  // Tool call events for memGPT timeline
  TOOL_CALL_START: "TOOL_CALL_START",
  TOOL_CALL_RESULT: "TOOL_CALL_RESULT",
} as const;

export type SSEEventType = (typeof SSEEventType)[keyof typeof SSEEventType];

/**
 * SSE Event payload from backend.
 */
export interface SSEEvent {
  event_type: SSEEventType;
  content: string;
  message_id?: string;
  // Tool call event fields
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  success?: boolean;
}

/**
 * Tool activity item for timeline display.
 */
export interface ToolActivity {
  id: string;
  timestamp: Date;
  tool_name: string;
  status: "running" | "success" | "error";
  content: string;
  tool_args?: Record<string, unknown>;
}

/**
 * Request body for sending a message.
 */
export interface SendMessageRequest {
  content: string;
}
