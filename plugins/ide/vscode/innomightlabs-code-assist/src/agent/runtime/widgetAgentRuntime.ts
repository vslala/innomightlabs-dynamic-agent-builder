import type { AgentRuntime, ConversationTurnRuntimeInput } from './agentRuntime';
import type { RuntimeCompletedEvent, RuntimeEvent } from './runtimeEvents';
import type { RuntimeToolCall, ToolDispatcher } from './toolDispatcher';
import { RegistryToolDispatcher } from './toolDispatcher';
import {
	type WidgetConversation,
	WidgetApiClient,
} from '../../integrations/widget/widgetApiClient';

export class WidgetAgentRuntime implements AgentRuntime {
	public constructor(
		private readonly widgetApiClient: WidgetApiClient,
		private readonly toolDispatcher: ToolDispatcher = new RegistryToolDispatcher(),
	) {}

	public async *run(input: ConversationTurnRuntimeInput): AsyncIterable<RuntimeEvent> {
		try {
			yield {
				type: 'status',
				step: input.progressLabels.loadConversations,
			};
			const existingConversations = await this.widgetApiClient.listConversations();

			yield {
				type: 'status',
				step: input.progressLabels.prepareConversation,
			};
			const selectedConversation = await this.resolveConversation(
				existingConversations,
				input.fallbackConversationTitle,
				input.preferredConversationId,
			);

			const finalText = yield* this.runConversationLoop(selectedConversation.conversationId, input);

			if (finalText.trim().length === 0) {
				throw new Error('The widget backend completed, but no assistant response text was returned.');
			}

			yield {
				type: 'final_text',
				text: finalText,
			};

			const refreshedConversations = await this.widgetApiClient.listConversations();
			yield {
				type: 'completed',
				conversationId: selectedConversation.conversationId,
				conversations: refreshedConversations,
				finalText,
			} satisfies RuntimeCompletedEvent;
		} catch (error) {
			yield {
				type: 'failed',
				message: error instanceof Error ? error.message : 'Unknown runtime error',
			};
		}
	}

	private async *runConversationLoop(
		conversationId: string,
		input: ConversationTurnRuntimeInput,
	): AsyncGenerator<RuntimeEvent, string> {
		let message = input.prompt;
		const maxTurns = input.maxTurns ?? 5;

		for (let turn = 0; turn < maxTurns; turn += 1) {
			yield {
				type: 'status',
				step: turn === 0
					? input.progressLabels.sendPrompt
					: input.progressLabels.sendToolResult?.('tool_result') ?? input.progressLabels.sendPrompt,
			};

			const streamedResponse = await this.widgetApiClient.sendMessage(conversationId, message);

			yield {
				type: 'status',
				step: input.progressLabels.finalize,
			};

			const responseText = streamedResponse.trim().length > 0
				? streamedResponse
				: await this.fetchLatestAssistantMessage(conversationId);

			const toolCall = this.parseToolCallEnvelope(responseText);
			if (!toolCall) {
				return responseText;
			}

			yield {
				type: 'tool_call_requested',
				callId: toolCall.callId,
				toolName: toolCall.toolName,
				input: toolCall.input,
			};

			yield {
				type: 'status',
				step: input.progressLabels.executeTool?.(toolCall.toolName)
					?? `Executing tool: ${toolCall.toolName}`,
			};

			const toolResult = await this.toolDispatcher.dispatch(toolCall);

			yield {
				type: 'tool_result_received',
				callId: toolResult.callId,
				toolName: toolResult.toolName,
				output: toolResult.output,
			};

			message = this.buildToolResultPrompt(toolCall, toolResult.output);
		}

		throw new Error('The agent runtime exceeded the maximum number of tool turns.');
	}

	private async resolveConversation(
		conversations: WidgetConversation[],
		fallbackTitle: string,
		preferredConversationId?: string | null,
	): Promise<WidgetConversation> {
		if (preferredConversationId) {
			const existing = conversations.find(
				(conversation) => conversation.conversationId === preferredConversationId,
			);
			if (existing) {
				return existing;
			}
		}

		if (conversations.length > 0) {
			return conversations[0];
		}

		return this.widgetApiClient.createConversation(fallbackTitle);
	}

	private async fetchLatestAssistantMessage(conversationId: string): Promise<string> {
		const payload = await this.widgetApiClient.getConversationMessages(conversationId);
		const assistantMessage = payload.find((message) => message.role === 'assistant');
		return assistantMessage?.content ?? '';
	}

	private parseToolCallEnvelope(responseText: string): RuntimeToolCall | null {
		const trimmed = responseText.trim();
		if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) {
			return null;
		}

		try {
			const payload = JSON.parse(trimmed) as Record<string, unknown>;
			if (payload.type !== 'tool_call') {
				return null;
			}

			if (typeof payload.toolName !== 'string' || payload.toolName.length === 0) {
				return null;
			}

			const callId = typeof payload.callId === 'string' && payload.callId.length > 0
				? payload.callId
				: `tool-${Date.now()}`;

			return {
				callId,
				toolName: payload.toolName,
				input: payload.input ?? {},
			};
		} catch {
			return null;
		}
	}

	private buildToolResultPrompt(call: RuntimeToolCall, output: unknown): string {
		return [
			'Tool result received. Continue the task using this data.',
			'If you need another tool, respond only with a JSON object like:',
			'{"type":"tool_call","toolName":"read_workspace_file","input":{"path":"src/example.ts"}}',
			'If you have enough information, return the final answer normally.',
			'',
			`Tool: ${call.toolName}`,
			`Call ID: ${call.callId}`,
			'Output:',
			JSON.stringify(output, null, 2),
		].join('\n');
	}
}
