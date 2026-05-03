import * as vscode from 'vscode';

import type { VisitorInfo } from '../auth/authService';
import type { ConversationMessage, ConversationSummary } from '../innomightlabsClient';
import type { AppState } from '../state/appState';
import { AppStore } from '../state/appStore';

type ConversationLogViewState = {
	auth: {
		isAuthenticated: boolean;
		isAuthenticating: boolean;
		visitor: VisitorInfo | null;
	};
	conversations: ConversationSummary[];
	selectedConversationId: string | null;
	messages: ConversationMessage[];
	isLoading: boolean;
	error: string | null;
};

type ConversationLogViewActions = {
	onRefresh: () => Promise<void>;
};

export class ConversationLogViewProvider implements vscode.WebviewViewProvider {
	private view?: vscode.WebviewView;
	private state: ConversationLogViewState = {
		auth: {
			isAuthenticated: false,
			isAuthenticating: false,
			visitor: null,
		},
		conversations: [],
		selectedConversationId: null,
		messages: [],
		isLoading: false,
		error: null,
	};

	public constructor(
		private readonly extensionUri: vscode.Uri,
		private readonly actions: ConversationLogViewActions,
		private readonly store: AppStore,
	) {}

	public resolveWebviewView(
		webviewView: vscode.WebviewView,
		_context: vscode.WebviewViewResolveContext,
		_token: vscode.CancellationToken,
	): void {
		this.view = webviewView;
		webviewView.webview.options = {
			enableScripts: true,
			localResourceRoots: [this.extensionUri],
		};
		webviewView.webview.onDidReceiveMessage(async (message: { type?: string }) => {
			if (message.type === 'refreshConversationLog') {
				await this.actions.onRefresh();
			}
		});
		this.store.subscribe((appState) => {
			this.state = this.mapAppState(appState);
			this.render();
		});
		this.render();
	}

	public setAuthState(auth: ConversationLogViewState['auth']): void {
		this.store.update((state) => ({
			...state,
			auth,
		}));
	}

	public setConversationState(
		conversations: ConversationSummary[],
		selectedConversationId: string | null,
	): void {
		this.store.update((state) => ({
			...state,
			conversations,
			selectedConversationId,
		}));
	}

	public showLoading(): void {
		this.store.update((state) => ({
			...state,
			conversationLog: {
				...state.conversationLog,
				isLoading: true,
				error: null,
			},
		}));
	}

	public showMessages(messages: ConversationMessage[]): void {
		this.store.update((state) => ({
			...state,
			conversationLog: {
				messages,
				isLoading: false,
				error: null,
			},
		}));
	}

	public showError(message: string): void {
		this.store.update((state) => ({
			...state,
			conversationLog: {
				messages: [],
				isLoading: false,
				error: message,
			},
		}));
	}

	public clearMessages(): void {
		this.store.update((state) => ({
			...state,
			conversationLog: {
				messages: [],
				isLoading: false,
				error: null,
			},
		}));
	}

	private mapAppState(appState: AppState): ConversationLogViewState {
		return {
			auth: appState.auth,
			conversations: appState.conversations,
			selectedConversationId: appState.selectedConversationId,
			messages: appState.conversationLog.messages,
			isLoading: appState.conversationLog.isLoading,
			error: appState.conversationLog.error,
		};
	}

	private render(): void {
		if (!this.view) {
			return;
		}

		this.view.webview.html = this.getHtml(this.state);
	}

	private getHtml(state: ConversationLogViewState): string {
		const nonce = this.createNonce();
		const title = this.getConversationTitle(state);
		const body = this.renderBody(state);

		return `<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8" />
	<meta name="viewport" content="width=device-width, initial-scale=1.0" />
	<style>
		:root {
			color-scheme: light dark;
		}

		body {
			font-family: var(--vscode-font-family);
			padding: 12px;
			margin: 0;
			color: var(--vscode-foreground);
			background: var(--vscode-sideBar-background);
		}

		.panel {
			display: grid;
			gap: 12px;
		}

		.card {
			padding: 12px;
			border-radius: 12px;
			background: color-mix(in srgb, var(--vscode-editor-background) 94%, transparent);
			border: 1px solid var(--vscode-panel-border);
		}

		.header-row {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 8px;
		}

		h2, h3, p {
			margin: 0;
		}

		.muted {
			color: var(--vscode-descriptionForeground);
		}

		.action-btn {
			border: 0;
			border-radius: 999px;
			padding: 8px 12px;
			font: inherit;
			background: var(--vscode-button-background);
			color: var(--vscode-button-foreground);
			cursor: pointer;
		}

		.action-btn:hover {
			background: var(--vscode-button-hoverBackground);
		}

		.action-btn:disabled {
			opacity: 0.6;
			cursor: default;
		}

		.log-list {
			display: grid;
			gap: 10px;
			max-height: calc(100vh - 150px);
			overflow-y: auto;
			padding-right: 4px;
		}

		.message {
			padding: 12px;
			border-radius: 12px;
			border: 1px solid var(--vscode-panel-border);
			background: color-mix(in srgb, var(--vscode-input-background) 74%, transparent);
		}

		.message.user {
			background: color-mix(in srgb, var(--vscode-button-background) 14%, var(--vscode-input-background));
		}

		.message.assistant {
			background: color-mix(in srgb, var(--vscode-textCodeBlock-background) 64%, transparent);
		}

		.message-header {
			display: flex;
			align-items: center;
			justify-content: space-between;
			gap: 8px;
			margin-bottom: 8px;
		}

		.role {
			font-size: 12px;
			font-weight: 700;
			letter-spacing: 0.04em;
			text-transform: uppercase;
			color: var(--vscode-descriptionForeground);
		}

		.timestamp {
			font-size: 11px;
			color: var(--vscode-descriptionForeground);
		}

		pre {
			margin: 0;
			white-space: pre-wrap;
			word-break: break-word;
			font-family: var(--vscode-editor-font-family);
			font-size: var(--vscode-editor-font-size);
		}
	</style>
</head>
<body>
	<div class="panel">
		<section class="card">
			<div class="header-row">
				<div>
					<h3>Conversation Log</h3>
					<p class="muted">${this.escapeHtml(title)}</p>
				</div>
				<button class="action-btn" data-action="refreshConversationLog" ${state.isLoading ? 'disabled' : ''}>Refresh</button>
			</div>
		</section>
		${body}
	</div>
	<script nonce="${nonce}">
		const vscode = acquireVsCodeApi();
		document.querySelector('[data-action="refreshConversationLog"]')?.addEventListener('click', () => {
			vscode.postMessage({ type: 'refreshConversationLog' });
		});
	</script>
</body>
</html>`;
	}

	private renderBody(state: ConversationLogViewState): string {
		if (!state.auth.isAuthenticated) {
			return `<section class="card"><p class="muted">Sign in to load conversation history.</p></section>`;
		}

		if (!state.selectedConversationId) {
			return `<section class="card"><p class="muted">Select or create a conversation to view its message history.</p></section>`;
		}

		if (state.isLoading) {
			return `<section class="card"><p class="muted">Loading conversation messages...</p></section>`;
		}

		if (state.error) {
			return `<section class="card"><p>${this.escapeHtml(state.error)}</p></section>`;
		}

		if (state.messages.length === 0) {
			return `<section class="card"><p class="muted">No messages have been sent in this conversation yet.</p></section>`;
		}

		const messages = state.messages
			.map((message) => {
				const timestamp = message.createdAt ? this.formatTimestamp(message.createdAt) : '';
				return `<article class="message ${this.escapeHtml(message.role)}">
					<div class="message-header">
						<span class="role">${this.escapeHtml(message.role)}</span>
						${timestamp ? `<span class="timestamp">${this.escapeHtml(timestamp)}</span>` : ''}
					</div>
					<pre>${this.escapeHtml(message.content)}</pre>
				</article>`;
			})
			.join('');

		return `<section class="log-list">${messages}</section>`;
	}

	private getConversationTitle(state: ConversationLogViewState): string {
		if (!state.selectedConversationId) {
			return 'No conversation selected';
		}

		const selected = state.conversations.find(
			(conversation) => conversation.conversationId === state.selectedConversationId,
		);
		return selected ? selected.title : 'Selected conversation';
	}

	private formatTimestamp(value: string): string {
		const date = new Date(value);
		return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
	}

	private escapeHtml(value: string): string {
		return value
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
			.replace(/'/g, '&#39;');
	}

	private createNonce(): string {
		return Math.random().toString(36).slice(2);
	}
}
