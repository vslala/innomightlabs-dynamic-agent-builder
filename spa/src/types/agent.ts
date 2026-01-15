export type AgentModel = "krishna-mini" | "krishna-memgpt";

export type MemoryBlockType = "read" | "read-write";

export interface MemoryBlock {
  id: string;
  agentId: string;
  name: string;
  type: MemoryBlockType;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export interface AgentTool {
  id: string;
  agentId: string;
  toolId: string;
  name: string;
  description: string;
  config: Record<string, string>;
  enabled: boolean;
  createdAt: string;
}

export interface LLMConfig {
  provider: string;
  model: string;
  apiKey: string;
}

export interface Agent {
  id: string;
  userId: string;
  name: string;
  persona: string;
  agentModel: AgentModel;
  llmConfig: LLMConfig;
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  agentId: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface Conversation {
  id: string;
  agentId: string;
  agentName: string;
  lastMessage?: string;
  lastMessageAt?: string;
  messageCount: number;
}
