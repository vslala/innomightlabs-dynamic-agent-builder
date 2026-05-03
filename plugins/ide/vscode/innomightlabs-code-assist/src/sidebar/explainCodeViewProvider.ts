import * as vscode from 'vscode';

import type { VisitorInfo } from '../auth/authService';
import type { ConversationSummary } from '../innomightlabsClient';
import type { AppState } from '../state/appState';
import { AppStore } from '../state/appStore';

type ExplainCodeViewState = {
	code: string;
	language: string;
	explanation: string;
	status: 'idle' | 'ready' | 'error';
	auth: {
		isAuthenticated: boolean;
		isAuthenticating: boolean;
		visitor: VisitorInfo | null;
	};
	conversations: ConversationSummary[];
	selectedConversationId: string | null;
	workflow: {
		visible: boolean;
		title: string;
		steps: string[];
		currentStep: string | null;
	};
};

type ExplainCodeViewActions = {
	onSignIn: () => Promise<void>;
	onSignOut: () => Promise<void>;
	onConversationSelected: (conversationId: string) => Promise<void>;
	onNewConversation: () => Promise<void>;
};

export class ExplainCodeViewProvider implements vscode.WebviewViewProvider {
	private view?: vscode.WebviewView;
	private state: ExplainCodeViewState = {
		code: '',
		language: '',
		explanation: 'Select a code snippet, right-click, and run Explain Code.',
		status: 'idle',
		auth: {
			isAuthenticated: false,
			isAuthenticating: false,
			visitor: null,
		},
		conversations: [],
		selectedConversationId: null,
		workflow: {
			visible: false,
			title: '',
			steps: [],
			currentStep: null,
		},
	};

	public constructor(
		private readonly extensionUri: vscode.Uri,
		private readonly actions: ExplainCodeViewActions,
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
		webviewView.webview.onDidReceiveMessage(async (message: { type?: string; conversationId?: string }) => {
			if (message.type === 'signIn') {
				await this.actions.onSignIn();
			}
			if (message.type === 'signOut') {
				await this.actions.onSignOut();
			}
			if (message.type === 'selectConversation' && message.conversationId) {
				await this.actions.onConversationSelected(message.conversationId);
			}
			if (message.type === 'newConversation') {
				await this.actions.onNewConversation();
			}
		});
		this.store.subscribe((appState) => {
			this.state = this.mapAppState(appState);
			this.render();
		});
		this.render();
	}

	public setAuthState(auth: ExplainCodeViewState['auth']): void {
		this.store.update((state) => ({
			...state,
			auth,
		}));
	}

	public setConversations(
		conversations: ConversationSummary[],
		selectedConversationId: string | null,
	): void {
		this.store.update((state) => ({
			...state,
			conversations,
			selectedConversationId,
		}));
	}

	public setSelectedConversation(conversationId: string | null): void {
		this.store.update((state) => ({
			...state,
			selectedConversationId: conversationId,
		}));
	}

	public showExplanation(input: { code: string; language: string; explanation: string }): void {
		this.store.update((state) => ({
			...state,
			explainPanel: {
				code: input.code,
				language: input.language,
				explanation: input.explanation,
				status: 'ready',
			},
		}));
	}

	public showError(message: string, code: string, language: string): void {
		this.store.update((state) => ({
			...state,
			explainPanel: {
				code,
				language,
				explanation: message,
				status: 'error',
			},
		}));
	}

	public showAuthenticationRequired(code: string, language: string): void {
		this.store.update((state) => ({
			...state,
			explainPanel: {
				code,
				language,
				explanation: 'Sign in with Google to start sending selected code to the Innomightlabs backend.',
				status: 'idle',
			},
		}));
	}

	public showPendingAuthentication(): void {
		this.store.update((state) => ({
			...state,
			explainPanel: {
				...state.explainPanel,
				explanation: 'Waiting for Google sign-in to complete in your browser...',
				status: 'idle',
			},
		}));
	}

	public showWorkflowOverlay(title: string, steps: string[]): void {
		this.store.update((state) => ({
			...state,
			workflow: {
				visible: true,
				title,
				steps,
				currentStep: steps[0] ?? null,
			},
		}));
	}

	public updateWorkflowStep(currentStep: string): void {
		this.store.update((state) => ({
			...state,
			workflow: {
				...state.workflow,
				currentStep,
			},
		}));
	}

	public hideWorkflowOverlay(): void {
		this.store.update((state) => ({
			...state,
			workflow: {
				visible: false,
				title: '',
				steps: [],
				currentStep: null,
			},
		}));
	}

	private mapAppState(appState: AppState): ExplainCodeViewState {
		return {
			code: appState.explainPanel.code,
			language: appState.explainPanel.language,
			explanation: appState.explainPanel.explanation,
			status: appState.explainPanel.status,
			auth: appState.auth,
			conversations: appState.conversations,
			selectedConversationId: appState.selectedConversationId,
			workflow: appState.workflow,
		};
	}

	private render(): void {
		if (!this.view) {
			return;
		}

		this.view.webview.html = this.getHtml(this.state);
	}

	private getHtml(state: ExplainCodeViewState): string {
		const nonce = this.createNonce();
		const title = this.escapeHtml(this.getTitle(state.status));
		const explanation = this.renderMarkdownLike(state.explanation);
		const authCard = this.renderAuthCard(state);
		const conversationsCard = this.renderConversationsCard(state);
		const codeBlock = state.code
			? `<details class="code-details">
				<summary>Selected code</summary>
				<pre><code>${this.escapeHtml(state.code)}</code></pre>
			</details>`
			: '<p class="muted">No code selected yet.</p>';
		const language = state.language
			? `<p class="meta">Language: <strong>${this.escapeHtml(state.language)}</strong></p>`
			: '';
		const workflowOverlay = this.renderWorkflowOverlay(state);

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
			padding: 16px;
			margin: 0;
			color: var(--vscode-foreground);
			background:
				radial-gradient(circle at top right, color-mix(in srgb, var(--vscode-button-background) 18%, transparent), transparent 35%),
				var(--vscode-sideBar-background);
		}

		h2, h3 {
			margin-top: 0;
		}

		.panel {
			display: grid;
			gap: 16px;
		}

		.card {
			padding: 14px;
			border-radius: 12px;
			background: color-mix(in srgb, var(--vscode-editor-background) 94%, transparent);
			border: 1px solid var(--vscode-panel-border);
			box-shadow: 0 10px 28px color-mix(in srgb, var(--vscode-editor-background) 65%, transparent);
		}

		.header-row,
		.toolbar-row {
			display: flex;
			gap: 10px;
			align-items: center;
			justify-content: space-between;
		}

		.toolbar-row {
			margin-top: 10px;
		}

		.meta, .muted {
			color: var(--vscode-descriptionForeground);
		}

		.conversation-select {
			width: 100%;
			background: var(--vscode-dropdown-background);
			color: var(--vscode-dropdown-foreground);
			border: 1px solid var(--vscode-dropdown-border);
			border-radius: 10px;
			padding: 10px 12px;
			font: inherit;
		}

		.code-details {
			border-radius: 10px;
			background: color-mix(in srgb, var(--vscode-textCodeBlock-background) 70%, transparent);
			border: 1px solid var(--vscode-panel-border);
			overflow: hidden;
		}

		.code-details summary {
			cursor: pointer;
			list-style: none;
			padding: 12px 14px;
			font-weight: 600;
		}

		.code-details summary::-webkit-details-marker {
			display: none;
		}

		.code-details summary::after {
			content: 'Show';
			float: right;
			font-weight: 400;
			color: var(--vscode-descriptionForeground);
		}

		.code-details[open] summary::after {
			content: 'Hide';
		}

		pre {
			overflow-x: auto;
			white-space: pre-wrap;
			background: var(--vscode-textCodeBlock-background);
			padding: 12px;
			border-radius: 10px;
			margin: 0;
		}

		code {
			font-family: var(--vscode-editor-font-family);
		}

		p, li {
			line-height: 1.5;
		}

		.action-btn {
			border: 0;
			border-radius: 999px;
			padding: 10px 14px;
			font: inherit;
			background: var(--vscode-button-background);
			color: var(--vscode-button-foreground);
			cursor: pointer;
		}

		.action-btn:hover {
			background: var(--vscode-button-hoverBackground);
		}

		.action-btn:disabled {
			opacity: 0.7;
			cursor: default;
		}

		.action-btn.secondary {
			background: var(--vscode-input-background);
			color: var(--vscode-foreground);
			border: 1px solid var(--vscode-panel-border);
		}

		.overlay {
			position: fixed;
			inset: 0;
			padding: 18px;
			background: color-mix(in srgb, var(--vscode-sideBar-background) 70%, transparent);
			backdrop-filter: blur(6px);
			display: flex;
			align-items: center;
			justify-content: center;
		}

		.overlay-card {
			width: min(420px, 100%);
			padding: 18px;
			border-radius: 16px;
			background: color-mix(in srgb, var(--vscode-editor-background) 96%, transparent);
			border: 1px solid var(--vscode-panel-border);
			box-shadow: 0 24px 60px color-mix(in srgb, black 30%, transparent);
		}

		.overlay-title {
			font-size: 16px;
			font-weight: 700;
			margin-bottom: 8px;
		}

		.step-list {
			display: grid;
			gap: 8px;
			margin-top: 14px;
		}

		.step-item {
			padding: 10px 12px;
			border-radius: 10px;
			background: color-mix(in srgb, var(--vscode-input-background) 84%, transparent);
			color: var(--vscode-descriptionForeground);
		}

		.step-item.active {
			color: var(--vscode-foreground);
			background: color-mix(in srgb, var(--vscode-button-background) 26%, var(--vscode-input-background));
			border: 1px solid color-mix(in srgb, var(--vscode-button-background) 40%, transparent);
		}

		.badge {
			display: inline-flex;
			align-items: center;
			gap: 6px;
			border-radius: 999px;
			padding: 4px 10px;
			background: color-mix(in srgb, var(--vscode-button-background) 18%, transparent);
			color: var(--vscode-descriptionForeground);
			font-size: 12px;
		}
	</style>
</head>
<body>
	<div class="panel">
		${authCard}
		${conversationsCard}
		<section class="card">
			<div class="header-row">
				<h2>${title}</h2>
				<span class="badge">${this.escapeHtml(state.status === 'error' ? 'Needs attention' : 'Latest response')}</span>
			</div>
			${language}
			<div>${explanation}</div>
		</section>
		<section class="card">
			${codeBlock}
		</section>
	</div>
	${workflowOverlay}
	<script nonce="${nonce}">
		const vscode = acquireVsCodeApi();
		document.querySelector('[data-action="signIn"]')?.addEventListener('click', () => {
			vscode.postMessage({ type: 'signIn' });
		});
		document.querySelector('[data-action="signOut"]')?.addEventListener('click', () => {
			vscode.postMessage({ type: 'signOut' });
		});
		document.querySelector('[data-action="newConversation"]')?.addEventListener('click', () => {
			vscode.postMessage({ type: 'newConversation' });
		});
		document.querySelector('[data-action="selectConversation"]')?.addEventListener('change', (event) => {
			const target = event.target;
			if (!(target instanceof HTMLSelectElement)) {
				return;
			}
			vscode.postMessage({ type: 'selectConversation', conversationId: target.value });
		});
	</script>
</body>
</html>`;
	}

	private renderAuthCard(state: ExplainCodeViewState): string {
		const auth = state.auth;
		if (!auth.isAuthenticated) {
			const label = auth.isAuthenticating ? 'Opening Google Sign-In...' : 'Sign In with Google';
			return `<section class="card">
				<h3>Google Sign-In</h3>
				<p class="muted">Authenticate with the same widget flow used by the frontend before sending code to the backend.</p>
				<button class="action-btn" data-action="signIn" ${auth.isAuthenticating ? 'disabled' : ''}>${this.escapeHtml(label)}</button>
			</section>`;
		}

		const visitorName = auth.visitor?.name || auth.visitor?.email || 'Signed in';
		const visitorEmail = auth.visitor?.email ? `<p class="meta">${this.escapeHtml(auth.visitor.email)}</p>` : '';
		return `<section class="card">
			<div class="header-row">
				<h3>Signed In</h3>
				<button class="action-btn secondary" data-action="signOut">Sign Out</button>
			</div>
			<p><strong>${this.escapeHtml(visitorName)}</strong></p>
			${visitorEmail}
		</section>`;
	}

	private renderConversationsCard(state: ExplainCodeViewState): string {
		if (!state.auth.isAuthenticated) {
			return '';
		}

		const options = state.conversations.length > 0
			? state.conversations
				.map((conversation) => {
					const selected = conversation.conversationId === state.selectedConversationId
						? 'selected'
						: '';
					const label = `${conversation.title} (${conversation.messageCount})`;
					return `<option value="${this.escapeHtml(conversation.conversationId)}" ${selected}>${this.escapeHtml(label)}</option>`;
				})
				.join('')
			: '<option value="">No conversations yet</option>';

		return `<section class="card">
			<div class="header-row">
				<h3>Conversations</h3>
				<button class="action-btn secondary" data-action="newConversation">New</button>
			</div>
			<p class="muted">Reuse an existing thread or start a fresh conversation before sending another explanation request.</p>
			<div class="toolbar-row">
				<select class="conversation-select" data-action="selectConversation" ${state.conversations.length === 0 ? 'disabled' : ''}>
					${options}
				</select>
			</div>
		</section>`;
	}

	private renderWorkflowOverlay(state: ExplainCodeViewState): string {
		if (!state.workflow.visible) {
			return '';
		}

		const steps = state.workflow.steps
			.map((step) => {
				const isActive = step === state.workflow.currentStep;
				return `<div class="step-item ${isActive ? 'active' : ''}">${this.escapeHtml(step)}</div>`;
			})
			.join('');

		return `<div class="overlay">
			<div class="overlay-card">
				<div class="overlay-title">${this.escapeHtml(state.workflow.title)}</div>
				<p class="muted">Working through the backend flow. This window disappears as soon as the response is ready.</p>
				<div class="step-list">${steps}</div>
			</div>
		</div>`;
	}

	private getTitle(status: ExplainCodeViewState['status']): string {
		switch (status) {
			case 'ready':
				return 'Code Explanation';
			case 'error':
				return 'Explanation Failed';
			case 'idle':
			default:
				return 'Explain Code';
		}
	}

	private renderMarkdownLike(value: string): string {
		const escaped = this.escapeHtml(value);
		const withCodeFences = escaped.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
		const blocks = withCodeFences
			.split(/\n{2,}/)
			.map((block) => block.trim())
			.filter((block) => block.length > 0)
			.map((block) => {
				if (block.startsWith('<pre><code>')) {
					return block;
				}

				if (block.includes('\n- ')) {
					const lines = block.split('\n').filter((line) => line.trim().length > 0);
					const items = lines
						.map((line) => line.replace(/^- /, '').trim())
						.map((line) => `<li>${line}</li>`)
						.join('');
					return `<ul>${items}</ul>`;
				}

				return `<p>${block.replace(/\n/g, '<br />')}</p>`;
			});

		return blocks.join('');
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
