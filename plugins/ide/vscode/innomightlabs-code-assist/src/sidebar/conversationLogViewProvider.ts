import * as fs from 'node:fs';
import * as path from 'node:path';
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
	private readonly templateHtml: string;
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
	) {
		this.templateHtml = fs.readFileSync(
			path.join(this.extensionUri.fsPath, 'media', 'conversationLogView.html'),
			'utf8',
		);
	}

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
		const cssUri = this.view?.webview.asWebviewUri(
			vscode.Uri.joinPath(this.extensionUri, 'media', 'conversationLogView.css'),
		).toString() ?? '';

		return this.templateHtml
			.replace('{{CSS_URI}}', cssUri)
			.replace('{{TITLE}}', this.escapeHtml(title))
			.replace('{{REFRESH_DISABLED}}', state.isLoading ? 'disabled' : '')
			.replace('{{BODY}}', body)
			.replace('{{NONCE}}', nonce);
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
