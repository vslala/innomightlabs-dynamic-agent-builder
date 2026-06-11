/**
 * Message types matching backend API.
 */

import type { FormSchema } from "./form";

export type MessageRole = "user" | "assistant" | "system";

/**
 * Allowed file extensions for attachments.
 * Must match backend ALLOWED_EXTENSIONS.
 */
export const ALLOWED_EXTENSIONS = [
  ".txt",
  ".md",
  ".csv",
  ".json",
  ".py",
  ".js",
  ".ts",
  ".tsx",
  ".jsx",
  ".java",
  ".go",
  ".rs",
  ".rb",
  ".php",
  ".html",
  ".css",
  ".xml",
  ".yaml",
  ".yml",
  ".sh",
  ".sql",
  ".c",
  ".cpp",
  ".h",
  ".xlsx",
  ".xls",
];

/**
 * Extensions that require special parsing (binary files).
 */
export const EXCEL_EXTENSIONS = [".xlsx", ".xls"];

export const MAX_FILE_SIZE = 100 * 1024; // 100KB per file
export const MAX_TOTAL_SIZE = 250 * 1024; // 250KB total
export const MAX_FILES = 5;

/**
 * Full attachment with content (for sending).
 */
export interface Attachment {
  filename: string;
  content: string;
  size: number;
}

/**
 * Attachment info without content (for display).
 */
export interface AttachmentInfo {
  filename: string;
  size: number;
}

export interface MessageImage {
  image_id: string;
  url?: string | null;
  preview_data_url?: string | null;
  filename: string;
  mime_type: string;
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  prompt?: string | null;
  revised_prompt?: string | null;
}

export interface Message {
  message_id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  attachments?: AttachmentInfo[];
  images?: MessageImage[];
  created_at: string;
}

/**
 * SSE Event types matching backend enum.
 */
export const SSEEventType = {
  LIFECYCLE_NOTIFICATION: "LIFECYCLE_NOTIFICATION",
  AGENT_RESPONSE_TO_USER: "AGENT_RESPONSE_TO_USER",
  AGENT_THOUGHTS: "AGENT_THOUGHTS",
  IMAGE_GENERATION_STARTED: "IMAGE_GENERATION_STARTED",
  IMAGE_GENERATION_PARTIAL: "IMAGE_GENERATION_PARTIAL",
  IMAGE_GENERATION_COMPLETE: "IMAGE_GENERATION_COMPLETE",
  UI_FORM_RENDER: "UI_FORM_RENDER",
  USER_MESSAGE_SAVED: "USER_MESSAGE_SAVED",
  ASSISTANT_MESSAGE_SAVED: "ASSISTANT_MESSAGE_SAVED",
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
  form?: FormSchema;
  submit_label?: string;
  form_id?: string;
  form_label?: string;
  // Tool call event fields
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  success?: boolean;
  image_b64?: string;
  image_mime_type?: string;
  image_url?: string;
  image_id?: string;
  image_filename?: string;
  image_width?: number;
  image_height?: number;
  images?: GeneratedImageResponse[];
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
  attachments?: Attachment[];
}

export interface GenerateImageRequest {
  prompt: string;
  size?: string;
  quality?: string;
  output_format?: "png" | "jpeg" | "webp";
}

export interface GeneratedImageResponse {
  image_id: string;
  url?: string | null;
  s3_key: string;
  filename: string;
  mime_type: string;
  width?: number | null;
  height?: number | null;
  size_bytes: number;
  prompt: string;
  revised_prompt?: string | null;
}

export interface GenerateImageResponse {
  agent_id: string;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  images: GeneratedImageResponse[];
}
