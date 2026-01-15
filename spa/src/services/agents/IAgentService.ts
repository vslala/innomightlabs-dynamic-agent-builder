import type {
  Agent,
  MemoryBlock,
  AgentTool,
  ChatMessage,
  Conversation,
} from "../../types/agent";

export interface CreateAgentInput {
  name: string;
  persona: string;
  agentModel: Agent["agentModel"];
  llmConfig: Agent["llmConfig"];
}

export interface UpdateAgentInput {
  name?: string;
  persona?: string;
  agentModel?: Agent["agentModel"];
  llmConfig?: Agent["llmConfig"];
}

export interface CreateMemoryBlockInput {
  agentId: string;
  name: string;
  type: MemoryBlock["type"];
  content: string;
}

export interface UpdateMemoryBlockInput {
  name?: string;
  content?: string;
}

export interface IAgentService {
  // Agents
  getAgents(): Promise<Agent[]>;
  getAgent(id: string): Promise<Agent | null>;
  createAgent(input: CreateAgentInput): Promise<Agent>;
  updateAgent(id: string, input: UpdateAgentInput): Promise<Agent>;
  deleteAgent(id: string): Promise<void>;

  // Memory Blocks
  getMemoryBlocks(agentId: string): Promise<MemoryBlock[]>;
  createMemoryBlock(input: CreateMemoryBlockInput): Promise<MemoryBlock>;
  updateMemoryBlock(id: string, input: UpdateMemoryBlockInput): Promise<MemoryBlock>;
  deleteMemoryBlock(id: string): Promise<void>;

  // Tools
  getAgentTools(agentId: string): Promise<AgentTool[]>;
  addToolToAgent(agentId: string, toolId: string, config: Record<string, string>): Promise<AgentTool>;
  updateAgentTool(id: string, config: Record<string, string>, enabled: boolean): Promise<AgentTool>;
  removeToolFromAgent(id: string): Promise<void>;

  // Conversations
  getConversations(): Promise<Conversation[]>;
  getMessages(agentId: string): Promise<ChatMessage[]>;
  sendMessage(agentId: string, content: string): Promise<ChatMessage>;
}
