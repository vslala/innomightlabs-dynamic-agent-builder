import * as path from 'path';

import { ExplainPromptBuilder, type ExplainPromptRequest } from './agent/prompts/explainPromptBuilder';
import { createDefaultRuntimeTools } from './agent/tools/contextTools';
import type { ToolDefinition } from './agent/tools/toolDefinition';
import { WidgetAgentRuntime } from './agent/runtime/widgetAgentRuntime';
import { RegistryToolDispatcher } from './agent/runtime/toolDispatcher';
import {
	RewriteSelectionPromptBuilder,
	type RewriteSelectionPromptRequest,
} from './agent/prompts/rewriteSelectionPromptBuilder';
import {
	SlashCommandPromptBuilder,
	type SlashCommandPromptRequest,
} from './agent/prompts/slashCommandPromptBuilder';
import { AuthService } from './auth/authService';
import { ExtensionConfigService } from './config/extensionConfigService';
import {
	type WidgetConversation,
	type WidgetMessage,
	WidgetApiClient,
} from './integrations/widget/widgetApiClient';
import type { RuntimeCompletedEvent, RuntimeEvent } from './agent/runtime/runtimeEvents';

type ExplainCodeRequest = ExplainPromptRequest;

type SlashCommandRequest = SlashCommandPromptRequest & {
	indentation: string;
};

type RewriteSelectionRequest = RewriteSelectionPromptRequest;

type ExplainCodeOptions = {
	conversationId?: string | null;
	onProgress?: (step: string) => void;
};

export type ConversationSummary = {
	conversationId: string;
	title: string;
	updatedAt: string | null;
	messageCount: number;
};

export type ExplainCodeResult = {
	explanation: string;
	conversationId: string;
	conversations: ConversationSummary[];
};

export type SlashCommandResult = {
	completion: string;
	conversationId: string;
	conversations: ConversationSummary[];
};

export type RewriteSelectionResult = {
	replacement: string;
	conversationId: string;
	conversations: ConversationSummary[];
};

export type ConversationMessage = {
	role: string;
	content: string;
	createdAt: string | null;
};

export class InnomightlabsClient {
	private readonly configService: ExtensionConfigService;
	private readonly widgetApiClient: WidgetApiClient;
	private readonly widgetAgentRuntime: WidgetAgentRuntime;
	private readonly runtimeTools: ToolDefinition[];
	private readonly explainPromptBuilder = new ExplainPromptBuilder();
	private readonly rewriteSelectionPromptBuilder = new RewriteSelectionPromptBuilder();
	private readonly slashCommandPromptBuilder = new SlashCommandPromptBuilder();

	/**
	 * High-level application client for extension features.
	 *
	 * Responsibilities:
	 * - validate feature prerequisites
	 * - choose or create a conversation
	 * - build feature-specific prompts
	 * - coordinate widget API calls
	 * - return UI-friendly results
	 */
	public constructor(
		private readonly authService: AuthService,
		configService: ExtensionConfigService,
	) {
		this.configService = configService;
		this.widgetApiClient = new WidgetApiClient(this.configService, authService);
		this.runtimeTools = createDefaultRuntimeTools();
		this.widgetAgentRuntime = new WidgetAgentRuntime(
			this.widgetApiClient,
			new RegistryToolDispatcher(this.runtimeTools),
		);
	}

	public async explainCode(
		request: ExplainCodeRequest,
		options: ExplainCodeOptions = {},
	): Promise<ExplainCodeResult> {
		const config = await this.configService.getConfig();
		const session = await this.authService.getValidSession();
		console.log('[innomightlabs-code-assist] config loaded', {
			baseUrl: config.baseUrl,
			hasApiKey: config.apiKey.length > 0,
			hasVisitorToken: session !== null,
		});

		if (!config.baseUrl || !config.apiKey) {
			return {
				explanation: this.buildMockExplanation(request),
				conversationId: '',
				conversations: [],
			};
		}

		if (!session) {
			throw new Error('No active visitor session found. Sign in with Google before using Explain Code.');
		}

		options.onProgress?.('Fetching agent configuration');
		const widgetConfig = await this.widgetApiClient.fetchWidgetConfig();

		options.onProgress?.('Loading conversations');
		const prompt = this.explainPromptBuilder.build(request, {
			agentName: widgetConfig.agentName,
			tools: this.runtimeTools,
		});
		const runtimeResult = await this.runConversationTurn(
			{
				prompt,
				preferredConversationId: options.conversationId,
				fallbackConversationTitle: `Explain ${path.basename(request.fileName)}`,
				progressLabels: {
					loadConversations: 'Loading conversations',
					prepareConversation: 'Preparing conversation',
					sendPrompt: 'Sending explain prompt',
					finalize: 'Finalizing response',
				},
			},
			options.onProgress,
		);

		return {
			explanation: runtimeResult.finalText,
			conversationId: runtimeResult.conversationId,
			conversations: runtimeResult.conversations.map((conversation) => this.toConversationSummary(conversation)),
		};
	}

	public async listAvailableConversations(): Promise<ConversationSummary[]> {
		if (!(await this.configService.isConfigured())) {
			return [];
		}

		const session = await this.authService.getValidSession();
		if (!session) {
			return [];
		}

		return this.listConversations();
	}

	public async createNewConversation(title = 'New Chat'): Promise<ConversationSummary> {
		return this.toConversationSummary(await this.widgetApiClient.createConversation(title));
	}

	public async getConversationMessages(conversationId: string): Promise<ConversationMessage[]> {
		if (!conversationId) {
			return [];
		}

		if (!(await this.configService.isConfigured())) {
			return [];
		}

		const session = await this.authService.getValidSession();
		if (!session) {
			return [];
		}

		return (await this.widgetApiClient.getConversationMessages(conversationId))
			.map((message) => this.toConversationMessage(message));
	}

	public async completeSlashCommand(
		request: SlashCommandRequest,
		options: ExplainCodeOptions = {},
	): Promise<SlashCommandResult> {
		await this.assertConfiguredBackend('Configure the backend base URL and API key before using slash commands.');
		await this.requireSession('No active visitor session found. Sign in with Google before using slash commands.');

		options.onProgress?.('Fetching agent configuration');
		const widgetConfig = await this.widgetApiClient.fetchWidgetConfig();

		options.onProgress?.('Loading conversations');
		const prompt = this.slashCommandPromptBuilder.build(request, {
			agentName: widgetConfig.agentName,
			tools: this.runtimeTools,
		});
		const runtimeResult = await this.runConversationTurn(
			{
				prompt,
				preferredConversationId: options.conversationId,
				fallbackConversationTitle: `Slash ${path.basename(request.fileName)}`,
				progressLabels: {
					loadConversations: 'Loading conversations',
					prepareConversation: 'Preparing conversation',
					sendPrompt: 'Sending code completion prompt',
					finalize: 'Finalizing response',
				},
			},
			options.onProgress,
		);

		return {
			completion: this.stripMarkdownFences(runtimeResult.finalText),
			conversationId: runtimeResult.conversationId,
			conversations: runtimeResult.conversations.map((conversation) => this.toConversationSummary(conversation)),
		};
	}

	public async rewriteSelection(
		request: RewriteSelectionRequest,
		options: ExplainCodeOptions = {},
	): Promise<RewriteSelectionResult> {
		await this.assertConfiguredBackend('Configure the backend base URL and API key before rewriting code.');
		await this.requireSession('No active visitor session found. Sign in with Google before rewriting code.');

		options.onProgress?.('Fetching agent configuration');
		const widgetConfig = await this.widgetApiClient.fetchWidgetConfig();

		options.onProgress?.('Loading conversations');
		const prompt = this.rewriteSelectionPromptBuilder.build(request, {
			agentName: widgetConfig.agentName,
			tools: this.runtimeTools,
		});
		const runtimeResult = await this.runConversationTurn(
			{
				prompt,
				preferredConversationId: options.conversationId,
				fallbackConversationTitle: `Rewrite ${path.basename(request.fileName)}`,
				progressLabels: {
					loadConversations: 'Loading conversations',
					prepareConversation: 'Preparing conversation',
					sendPrompt: 'Sending rewrite prompt',
					finalize: 'Finalizing response',
				},
			},
			options.onProgress,
		);

		return {
			replacement: this.stripMarkdownFences(runtimeResult.finalText),
			conversationId: runtimeResult.conversationId,
			conversations: runtimeResult.conversations.map((conversation) => this.toConversationSummary(conversation)),
		};
	}

	private async listConversations(): Promise<ConversationSummary[]> {
		return (await this.widgetApiClient.listConversations())
			.map((conversation) => this.toConversationSummary(conversation));
	}

	private async assertConfiguredBackend(message: string): Promise<void> {
		if (!(await this.configService.isConfigured())) {
			throw new Error(message);
		}
	}

	private async requireSession(message: string): Promise<void> {
		const session = await this.authService.getValidSession();
		if (!session) {
			throw new Error(message);
		}
	}

	private toConversationSummary(conversation: WidgetConversation): ConversationSummary {
		return {
			conversationId: conversation.conversationId,
			title: conversation.title,
			updatedAt: conversation.updatedAt,
			messageCount: conversation.messageCount,
		};
	}

	private toConversationMessage(message: WidgetMessage): ConversationMessage {
		return {
			role: message.role,
			content: message.content,
			createdAt: message.createdAt,
		};
	}

	private buildMockExplanation(request: ExplainCodeRequest): string {
		return [
			'Mock response: configure `innomightlabsCodeAssist.apiBaseUrl` and `innomightlabsCodeAssist.apiKey` to call the real backend.',
			'',
			`Question: ${request.userQuestion}`,
			'',
			`Language: ${request.language}`,
			`File: ${request.fileName}`,
			'',
			'What this selected code appears to do:',
			'- It is a user-selected snippet captured from the active editor.',
			'- The extension is ready to send it to the backend once settings are configured.',
			'- The explanation is currently mocked so you can verify the command and sidebar flow first.',
			'',
			'Selected snippet preview:',
			'```',
			request.code,
			'```',
		].join('\n');
	}

	private stripMarkdownFences(value: string): string {
		const trimmed = value.trim();
		const fenced = trimmed.match(/^```[a-zA-Z0-9_-]*\n([\s\S]*?)\n```$/);
		return fenced ? fenced[1].trimEnd() : trimmed;
	}

	private async runConversationTurn(
		input: Parameters<WidgetAgentRuntime['run']>[0],
		onProgress?: (step: string) => void,
	): Promise<RuntimeCompletedEvent> {
		let completedEvent: RuntimeCompletedEvent | null = null;

		for await (const event of this.widgetAgentRuntime.run(input)) {
			this.handleRuntimeEvent(event, onProgress);
			if (event.type === 'completed') {
				completedEvent = event;
			}
		}

		if (!completedEvent) {
			throw new Error('The agent runtime completed without returning a final result.');
		}

		return completedEvent;
	}

	private handleRuntimeEvent(event: RuntimeEvent, onProgress?: (step: string) => void): void {
		switch (event.type) {
			case 'status':
				onProgress?.(event.step);
				return;
			case 'failed':
				throw new Error(event.message);
			case 'tool_call_requested':
			case 'tool_result_received':
			case 'final_text':
			case 'completed':
				return;
		}
	}
}
