import type { AuthService } from '../../auth/authService';
import type { ExtensionConfig, ExtensionConfigService } from '../../config/extensionConfigService';

export type WidgetConfig = {
	agentName: string;
	agentId: string;
	welcomeMessage: string | null;
	theme: Record<string, unknown>;
};

export type WidgetConversation = {
	conversationId: string;
	title: string;
	updatedAt: string | null;
	messageCount: number;
};

export type WidgetMessage = {
	role: string;
	content: string;
	createdAt: string | null;
};

type WidgetConfigResponse = {
	agent_name: string;
	agent_id: string;
	welcome_message?: string | null;
	theme?: Record<string, unknown>;
};

type WidgetConversationResponse = {
	conversation_id: string;
	title: string;
	created_at: string;
	updated_at?: string | null;
	message_count?: number;
};

type WidgetMessageResponse = {
	role: string;
	content: string;
	created_at?: string | null;
};

export class WidgetApiClient {
	public constructor(
		private readonly configService: ExtensionConfigService,
		private readonly authService: AuthService,
	) {}

	public getConfig(): ExtensionConfig {
		return this.configService.getConfig();
	}

	public async fetchWidgetConfig(): Promise<WidgetConfig> {
		const config = this.requireConfiguredBackend();
		const response = await fetch(`${config.baseUrl}/widget/config`, {
			method: 'GET',
			headers: {
				'x-api-key': config.apiKey,
			},
		});

		if (!response.ok) {
			throw new Error(`Widget config request failed: ${response.status} ${response.statusText}`);
		}

		const payload = (await response.json()) as WidgetConfigResponse;
		if (typeof payload.agent_name !== 'string' || typeof payload.agent_id !== 'string') {
			throw new Error('Widget config response did not include the expected fields.');
		}

		return {
			agentName: payload.agent_name,
			agentId: payload.agent_id,
			welcomeMessage: payload.welcome_message ?? null,
			theme: payload.theme ?? {},
		};
	}

	public async listConversations(): Promise<WidgetConversation[]> {
		const config = this.requireConfiguredBackend();
		const response = await fetch(`${config.baseUrl}/widget/conversations`, {
			method: 'GET',
			headers: await this.buildWidgetHeaders(config),
		});

		if (!response.ok) {
			throw new Error(`List conversations failed: ${response.status} ${response.statusText}`);
		}

		const payload = (await response.json()) as WidgetConversationResponse[];
		return payload.map((conversation) => this.toConversation(conversation));
	}

	public async createConversation(title: string): Promise<WidgetConversation> {
		const config = this.requireConfiguredBackend();
		const response = await fetch(`${config.baseUrl}/widget/conversations`, {
			method: 'POST',
			headers: await this.buildWidgetHeaders(config),
			body: JSON.stringify({ title }),
		});

		if (!response.ok) {
			throw new Error(`Create conversation failed: ${response.status} ${response.statusText}`);
		}

		const payload = (await response.json()) as WidgetConversationResponse;
		if (typeof payload.conversation_id !== 'string' || payload.conversation_id.length === 0) {
			throw new Error('Conversation response did not include a conversation_id.');
		}

		return this.toConversation(payload);
	}

	public async sendMessage(conversationId: string, content: string): Promise<string> {
		const config = this.requireConfiguredBackend();
		const response = await fetch(
			`${config.baseUrl}/widget/conversations/${conversationId}/messages`,
			{
				method: 'POST',
				headers: await this.buildWidgetHeaders(config),
				body: JSON.stringify({ content }),
			},
		);

		if (!response.ok) {
			throw new Error(await this.buildRequestError('Send message failed', response));
		}

		if (!response.body) {
			return '';
		}

		return this.readSseResponse(response.body);
	}

	public async getConversationMessages(conversationId: string): Promise<WidgetMessage[]> {
		const config = this.requireConfiguredBackend();
		const response = await fetch(
			`${config.baseUrl}/widget/conversations/${conversationId}/messages`,
			{
				method: 'GET',
				headers: await this.buildWidgetHeaders(config),
			},
		);

		if (!response.ok) {
			throw new Error(await this.buildRequestError('Load conversation messages failed', response));
		}

		const payload = (await response.json()) as WidgetMessageResponse[];
		return payload.map((message) => ({
			role: message.role,
			content: message.content,
			createdAt: message.created_at ?? null,
		}));
	}

	private requireConfiguredBackend(): ExtensionConfig {
		const config = this.configService.getConfig();
		if (!config.baseUrl || !config.apiKey) {
			throw new Error('Configure the backend base URL and API key before calling the widget API.');
		}
		return config;
	}

	private async buildWidgetHeaders(config: ExtensionConfig): Promise<Record<string, string>> {
		const session = await this.authService.getValidSession();
		if (!session) {
			throw new Error('No active visitor session found. Sign in with Google before using the widget API.');
		}

		return {
			'Content-Type': 'application/json',
			'x-api-key': config.apiKey,
			Authorization: `Bearer ${session.token}`,
		};
	}

	private toConversation(conversation: WidgetConversationResponse): WidgetConversation {
		return {
			conversationId: conversation.conversation_id,
			title: conversation.title,
			updatedAt: conversation.updated_at ?? conversation.created_at ?? null,
			messageCount: conversation.message_count ?? 0,
		};
	}

	private async readSseResponse(stream: ReadableStream<Uint8Array>): Promise<string> {
		const reader = stream.getReader();
		const decoder = new TextDecoder();
		let buffer = '';
		let result = '';

		while (true) {
			const chunk = await reader.read();
			if (chunk.done) {
				break;
			}

			buffer += decoder.decode(chunk.value, { stream: true });
			const events = buffer.split('\n\n');
			buffer = events.pop() ?? '';

			for (const eventBlock of events) {
				result += this.extractTextFromEventBlock(eventBlock);
			}
		}

		if (buffer.trim().length > 0) {
			result += this.extractTextFromEventBlock(buffer);
		}

		return result.trim();
	}

	private extractTextFromEventBlock(eventBlock: string): string {
		const lines = eventBlock
			.split('\n')
			.map((line) => line.trim())
			.filter((line) => line.length > 0);
		const dataLines = lines
			.filter((line) => line.startsWith('data:'))
			.map((line) => line.slice(5).trim());

		if (dataLines.length === 0) {
			return '';
		}

		const payloadText = dataLines.join('\n');
		if (payloadText === '[DONE]') {
			return '';
		}

		try {
			const payload = JSON.parse(payloadText) as unknown;
			return this.extractTextFromPayload(payload);
		} catch {
			return `${payloadText}\n`;
		}
	}

	private extractTextFromPayload(payload: unknown): string {
		if (typeof payload === 'string') {
			return payload;
		}

		if (!payload || typeof payload !== 'object') {
			return '';
		}

		const record = payload as Record<string, unknown>;
		if (
			typeof record.event_type === 'string' &&
			record.event_type !== 'AGENT_RESPONSE_TO_USER'
		) {
			return '';
		}

		const textKeys = ['content', 'text', 'delta', 'response'];
		for (const key of textKeys) {
			const value = record[key];
			if (typeof value === 'string') {
				return value;
			}
		}

		if (record.message && typeof record.message === 'object') {
			const nested = this.extractTextFromPayload(record.message);
			if (nested) {
				return nested;
			}
		}

		if (record.data && typeof record.data === 'object') {
			const nested = this.extractTextFromPayload(record.data);
			if (nested) {
				return nested;
			}
		}

		return '';
	}

	private async buildRequestError(prefix: string, response: Response): Promise<string> {
		try {
			const payload = (await response.json()) as { detail?: unknown };
			if (typeof payload.detail === 'string' && payload.detail.length > 0) {
				return `${prefix}: ${payload.detail}`;
			}

			if (Array.isArray(payload.detail) && payload.detail.length > 0) {
				const message = payload.detail
					.map((item) => {
						if (!item || typeof item !== 'object') {
							return '';
						}
						const record = item as Record<string, unknown>;
						return typeof record.msg === 'string' ? record.msg : '';
					})
					.filter((item) => item.length > 0)
					.join('; ');
				if (message.length > 0) {
					return `${prefix}: ${message}`;
				}
			}
		} catch {
			// Fall through to generic error.
		}

		return `${prefix}: ${response.status} ${response.statusText}`;
	}
}
