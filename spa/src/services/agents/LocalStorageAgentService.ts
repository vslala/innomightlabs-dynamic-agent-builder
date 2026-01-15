import type {
  Agent,
  MemoryBlock,
  AgentTool,
  ChatMessage,
  Conversation,
} from "../../types/agent";
import type {
  IAgentService,
  CreateAgentInput,
  UpdateAgentInput,
  CreateMemoryBlockInput,
  UpdateMemoryBlockInput,
} from "./IAgentService";

const STORAGE_KEYS = {
  AGENTS: "innomight_agents",
  MEMORY_BLOCKS: "innomight_memory_blocks",
  AGENT_TOOLS: "innomight_agent_tools",
  MESSAGES: "innomight_messages",
};

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

function getFromStorage<T>(key: string): T[] {
  const data = localStorage.getItem(key);
  return data ? JSON.parse(data) : [];
}

function saveToStorage<T>(key: string, data: T[]): void {
  localStorage.setItem(key, JSON.stringify(data));
}

export class LocalStorageAgentService implements IAgentService {
  // Agents
  async getAgents(): Promise<Agent[]> {
    return getFromStorage<Agent>(STORAGE_KEYS.AGENTS);
  }

  async getAgent(id: string): Promise<Agent | null> {
    const agents = await this.getAgents();
    return agents.find((a) => a.id === id) || null;
  }

  async createAgent(input: CreateAgentInput): Promise<Agent> {
    const agents = await this.getAgents();
    const now = new Date().toISOString();

    const newAgent: Agent = {
      id: generateId(),
      userId: "current-user", // In real app, get from auth context
      name: input.name,
      persona: input.persona,
      agentModel: input.agentModel,
      llmConfig: input.llmConfig,
      createdAt: now,
      updatedAt: now,
    };

    agents.push(newAgent);
    saveToStorage(STORAGE_KEYS.AGENTS, agents);
    return newAgent;
  }

  async updateAgent(id: string, input: UpdateAgentInput): Promise<Agent> {
    const agents = await this.getAgents();
    const index = agents.findIndex((a) => a.id === id);

    if (index === -1) {
      throw new Error("Agent not found");
    }

    const updatedAgent: Agent = {
      ...agents[index],
      ...input,
      updatedAt: new Date().toISOString(),
    };

    agents[index] = updatedAgent;
    saveToStorage(STORAGE_KEYS.AGENTS, agents);
    return updatedAgent;
  }

  async deleteAgent(id: string): Promise<void> {
    const agents = await this.getAgents();
    const filtered = agents.filter((a) => a.id !== id);
    saveToStorage(STORAGE_KEYS.AGENTS, filtered);

    // Also delete related memory blocks, tools, and messages
    const memoryBlocks = await this.getMemoryBlocks(id);
    for (const block of memoryBlocks) {
      await this.deleteMemoryBlock(block.id);
    }

    const tools = await this.getAgentTools(id);
    for (const tool of tools) {
      await this.removeToolFromAgent(tool.id);
    }

    // Delete messages
    const allMessages = getFromStorage<ChatMessage>(STORAGE_KEYS.MESSAGES);
    const filteredMessages = allMessages.filter((m) => m.agentId !== id);
    saveToStorage(STORAGE_KEYS.MESSAGES, filteredMessages);
  }

  // Memory Blocks
  async getMemoryBlocks(agentId: string): Promise<MemoryBlock[]> {
    const blocks = getFromStorage<MemoryBlock>(STORAGE_KEYS.MEMORY_BLOCKS);
    return blocks.filter((b) => b.agentId === agentId);
  }

  async createMemoryBlock(input: CreateMemoryBlockInput): Promise<MemoryBlock> {
    const blocks = getFromStorage<MemoryBlock>(STORAGE_KEYS.MEMORY_BLOCKS);
    const now = new Date().toISOString();

    const newBlock: MemoryBlock = {
      id: generateId(),
      agentId: input.agentId,
      name: input.name,
      type: input.type,
      content: input.content,
      createdAt: now,
      updatedAt: now,
    };

    blocks.push(newBlock);
    saveToStorage(STORAGE_KEYS.MEMORY_BLOCKS, blocks);
    return newBlock;
  }

  async updateMemoryBlock(
    id: string,
    input: UpdateMemoryBlockInput
  ): Promise<MemoryBlock> {
    const blocks = getFromStorage<MemoryBlock>(STORAGE_KEYS.MEMORY_BLOCKS);
    const index = blocks.findIndex((b) => b.id === id);

    if (index === -1) {
      throw new Error("Memory block not found");
    }

    const updatedBlock: MemoryBlock = {
      ...blocks[index],
      ...input,
      updatedAt: new Date().toISOString(),
    };

    blocks[index] = updatedBlock;
    saveToStorage(STORAGE_KEYS.MEMORY_BLOCKS, blocks);
    return updatedBlock;
  }

  async deleteMemoryBlock(id: string): Promise<void> {
    const blocks = getFromStorage<MemoryBlock>(STORAGE_KEYS.MEMORY_BLOCKS);
    const filtered = blocks.filter((b) => b.id !== id);
    saveToStorage(STORAGE_KEYS.MEMORY_BLOCKS, filtered);
  }

  // Tools
  async getAgentTools(agentId: string): Promise<AgentTool[]> {
    const tools = getFromStorage<AgentTool>(STORAGE_KEYS.AGENT_TOOLS);
    return tools.filter((t) => t.agentId === agentId);
  }

  async addToolToAgent(
    agentId: string,
    toolId: string,
    config: Record<string, string>
  ): Promise<AgentTool> {
    const tools = getFromStorage<AgentTool>(STORAGE_KEYS.AGENT_TOOLS);

    // Mock tool data - in real app, fetch from tool store
    const toolInfo: Record<string, { name: string; description: string }> = {
      wordpress: {
        name: "WordPress",
        description: "Manage WordPress sites - create posts, pages, and more",
      },
      gmail: {
        name: "Gmail",
        description: "Send and read emails via Gmail API",
      },
      slack: {
        name: "Slack",
        description: "Send messages and manage Slack channels",
      },
    };

    const info = toolInfo[toolId] || { name: toolId, description: "" };

    const newTool: AgentTool = {
      id: generateId(),
      agentId,
      toolId,
      name: info.name,
      description: info.description,
      config,
      enabled: true,
      createdAt: new Date().toISOString(),
    };

    tools.push(newTool);
    saveToStorage(STORAGE_KEYS.AGENT_TOOLS, tools);
    return newTool;
  }

  async updateAgentTool(
    id: string,
    config: Record<string, string>,
    enabled: boolean
  ): Promise<AgentTool> {
    const tools = getFromStorage<AgentTool>(STORAGE_KEYS.AGENT_TOOLS);
    const index = tools.findIndex((t) => t.id === id);

    if (index === -1) {
      throw new Error("Tool not found");
    }

    const updatedTool: AgentTool = {
      ...tools[index],
      config,
      enabled,
    };

    tools[index] = updatedTool;
    saveToStorage(STORAGE_KEYS.AGENT_TOOLS, tools);
    return updatedTool;
  }

  async removeToolFromAgent(id: string): Promise<void> {
    const tools = getFromStorage<AgentTool>(STORAGE_KEYS.AGENT_TOOLS);
    const filtered = tools.filter((t) => t.id !== id);
    saveToStorage(STORAGE_KEYS.AGENT_TOOLS, filtered);
  }

  // Conversations
  async getConversations(): Promise<Conversation[]> {
    const agents = await this.getAgents();
    const messages = getFromStorage<ChatMessage>(STORAGE_KEYS.MESSAGES);

    return agents.map((agent) => {
      const agentMessages = messages
        .filter((m) => m.agentId === agent.id)
        .sort(
          (a, b) =>
            new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
        );

      const lastMessage = agentMessages[0];

      return {
        id: agent.id,
        agentId: agent.id,
        agentName: agent.name,
        lastMessage: lastMessage?.content,
        lastMessageAt: lastMessage?.timestamp,
        messageCount: agentMessages.length,
      };
    });
  }

  async getMessages(agentId: string): Promise<ChatMessage[]> {
    const messages = getFromStorage<ChatMessage>(STORAGE_KEYS.MESSAGES);
    return messages
      .filter((m) => m.agentId === agentId)
      .sort(
        (a, b) =>
          new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );
  }

  async sendMessage(agentId: string, content: string): Promise<ChatMessage> {
    const messages = getFromStorage<ChatMessage>(STORAGE_KEYS.MESSAGES);

    // Add user message
    const userMessage: ChatMessage = {
      id: generateId(),
      agentId,
      role: "user",
      content,
      timestamp: new Date().toISOString(),
    };
    messages.push(userMessage);

    // Simulate agent response (in real app, this would call the backend)
    const agentResponse: ChatMessage = {
      id: generateId(),
      agentId,
      role: "assistant",
      content: `This is a simulated response to: "${content}". In the real application, this would be processed by the agent.`,
      timestamp: new Date(Date.now() + 1000).toISOString(),
    };
    messages.push(agentResponse);

    saveToStorage(STORAGE_KEYS.MESSAGES, messages);
    return userMessage;
  }
}
