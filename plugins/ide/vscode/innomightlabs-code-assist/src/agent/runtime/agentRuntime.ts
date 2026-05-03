import type { RuntimeEvent } from './runtimeEvents';

export type ConversationTurnRuntimeInput = {
	prompt: string;
	preferredConversationId?: string | null;
	fallbackConversationTitle: string;
	maxTurns?: number;
	progressLabels: {
		loadConversations: string;
		prepareConversation: string;
		sendPrompt: string;
		finalize: string;
		executeTool?: (toolName: string) => string;
		sendToolResult?: (toolName: string) => string;
	};
};

export interface AgentRuntime {
	run(input: ConversationTurnRuntimeInput): AsyncIterable<RuntimeEvent>;
}
