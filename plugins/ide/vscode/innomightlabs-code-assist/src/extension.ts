import * as vscode from 'vscode';

import { CompleteSlashCommandUseCase } from './application/useCases/completeSlashCommandUseCase';
import { ExplainCodeUseCase } from './application/useCases/explainCodeUseCase';
import { RewriteSelectionUseCase } from './application/useCases/rewriteSelectionUseCase';
import { AuthService, type AuthState } from './auth/authService';
import { ExtensionConfigService } from './config/extensionConfigService';
import { type ConversationSummary, InnomightlabsClient } from './innomightlabsClient';
import { ConversationLogViewProvider } from './sidebar/conversationLogViewProvider';
import { ExplainCodeViewProvider } from './sidebar/explainCodeViewProvider';
import { AppStore } from './state/appStore';

const EXPLAIN_CODE_COMMAND = 'innomightlabs-code-assist.explainCode';
const REWRITE_SELECTION_COMMAND = 'innomightlabs-code-assist.rewriteSelection';
const SIGN_IN_COMMAND = 'innomightlabs-code-assist.signIn';
const SIGN_OUT_COMMAND = 'innomightlabs-code-assist.signOut';
const CONFIGURE_BACKEND_COMMAND = 'innomightlabs-code-assist.configureBackend';
const EXPLAIN_CODE_VIEW_ID = 'innomightlabs-code-assist.explainCodeView';
const CONVERSATION_LOG_VIEW_ID = 'innomightlabs-code-assist.conversationLogView';

export function activate(context: vscode.ExtensionContext): void {
	const configService = new ExtensionConfigService(context);
	const authService = new AuthService(context, configService);
	const client = new InnomightlabsClient(authService, configService);
	const store = new AppStore();
	let selectedConversationId: string | null = null;
	let latestConversations: ConversationSummary[] = [];

	const conversationLogViewProvider = new ConversationLogViewProvider(context.extensionUri, {
		onRefresh: async () => {
			await refreshConversationLog();
		},
	}, store);

	const explainCodeViewProvider = new ExplainCodeViewProvider(context.extensionUri, {
		onSignIn: async () => {
			await runSignIn(authService, explainCodeViewProvider);
		},
		onConfigureBackend: async () => {
			await runConfigureBackend(configService);
		},
		onSignOut: async () => {
			selectedConversationId = null;
			latestConversations = [];
			store.update((state) => ({
				...state,
				conversations: [],
				selectedConversationId: null,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: null,
				},
			}));
			await authService.signOut();
		},
		onConversationSelected: async (conversationId: string) => {
			explainCodeViewProvider.setSelectedConversation(conversationId);
			await updateConversationState(latestConversations, conversationId);
		},
		onNewConversation: async () => {
			try {
				explainCodeViewProvider.showWorkflowOverlay('Creating conversation', [
					'Creating a fresh conversation on the backend',
				]);
				const created = await client.createNewConversation();
				const conversations = await client.listAvailableConversations();
				await updateConversationState(conversations, created.conversationId);
			} catch (error) {
				const message = error instanceof Error ? error.message : 'Unknown error';
				explainCodeViewProvider.showError(message, '', '');
				vscode.window.showErrorMessage(`Failed to create conversation: ${message}`);
			} finally {
				explainCodeViewProvider.hideWorkflowOverlay();
			}
		},
	}, store);

	const refreshConversations = async (): Promise<void> => {
		const conversations = await client.listAvailableConversations();
		latestConversations = conversations;
		if (conversations.length === 0) {
			selectedConversationId = null;
			store.update((state) => ({
				...state,
				conversations: [],
				selectedConversationId: null,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: null,
				},
			}));
			return;
		}

		const hasSelected = selectedConversationId
			? conversations.some((conversation) => conversation.conversationId === selectedConversationId)
			: false;
		selectedConversationId = hasSelected
			? selectedConversationId
			: conversations[0].conversationId;
		store.update((state) => ({
			...state,
			conversations,
			selectedConversationId,
		}));
		await refreshConversationLog();
	};

	const updateConversationState = async (
		conversations: ConversationSummary[],
		conversationId: string | null,
	): Promise<void> => {
		latestConversations = conversations;
		selectedConversationId = conversationId;
		store.update((state) => ({
			...state,
			conversations,
			selectedConversationId: conversationId,
		}));
		await refreshConversationLog();
	};

	const refreshConversationLog = async (): Promise<void> => {
		if (!selectedConversationId) {
			store.update((state) => ({
				...state,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: null,
				},
			}));
			return;
		}

		const authState = await authService.getAuthState();
		if (!authState.isAuthenticated) {
			store.update((state) => ({
				...state,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: null,
				},
			}));
			return;
		}

		store.update((state) => ({
			...state,
			conversationLog: {
				...state.conversationLog,
				isLoading: true,
				error: null,
			},
		}));
		try {
			const messages = await client.getConversationMessages(selectedConversationId);
			store.update((state) => ({
				...state,
				conversationLog: {
					messages,
					isLoading: false,
					error: null,
				},
			}));
		} catch (error) {
			const message = error instanceof Error ? error.message : 'Unknown error';
			store.update((state) => ({
				...state,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: message,
				},
			}));
		}
	};

	const explainCodeUseCase = new ExplainCodeUseCase({
		client,
		authService,
		view: explainCodeViewProvider,
		getSelectedConversationId: () => selectedConversationId,
		syncConversationState: updateConversationState,
		setLatestResult: (result) => {
			selectedConversationId = result.conversationId;
		},
	});

	const rewriteSelectionUseCase = new RewriteSelectionUseCase({
		client,
		authService,
		view: explainCodeViewProvider,
		getSelectedConversationId: () => selectedConversationId,
		syncConversationState: updateConversationState,
		setLatestResult: (result) => {
			selectedConversationId = result.conversationId;
		},
	});

	const completeSlashCommandUseCase = new CompleteSlashCommandUseCase({
		client,
		authService,
		view: explainCodeViewProvider,
		getSelectedConversationId: () => selectedConversationId,
		syncConversationState: updateConversationState,
		setLatestResult: (result) => {
			selectedConversationId = result.conversationId;
		},
	});

	context.subscriptions.push(
		vscode.window.registerUriHandler(authService),
		vscode.window.registerWebviewViewProvider(EXPLAIN_CODE_VIEW_ID, explainCodeViewProvider),
		vscode.window.registerWebviewViewProvider(CONVERSATION_LOG_VIEW_ID, conversationLogViewProvider),
		vscode.commands.registerCommand(EXPLAIN_CODE_COMMAND, async () => {
			await explainCodeUseCase.execute();
		}),
		vscode.commands.registerCommand(REWRITE_SELECTION_COMMAND, async () => {
			await rewriteSelectionUseCase.execute();
		}),
		vscode.commands.registerCommand(SIGN_IN_COMMAND, async () => {
			await runSignIn(authService, explainCodeViewProvider);
		}),
		vscode.commands.registerCommand(SIGN_OUT_COMMAND, async () => {
			selectedConversationId = null;
			latestConversations = [];
			store.update((state) => ({
				...state,
				conversations: [],
				selectedConversationId: null,
				conversationLog: {
					messages: [],
					isLoading: false,
					error: null,
				},
			}));
			await authService.signOut();
		}),
		vscode.commands.registerCommand(CONFIGURE_BACKEND_COMMAND, async () => {
			await runConfigureBackend(configService);
		}),
		authService.onDidChangeAuthState(async (state: AuthState) => {
			store.update((current) => ({
				...current,
				auth: state,
			}));
			if (state.isAuthenticated) {
				await refreshConversations();
			} else {
				if (!state.isAuthenticating) {
					explainCodeViewProvider.clearPendingAuthentication();
				}
				selectedConversationId = null;
				latestConversations = [];
				store.update((current) => ({
					...current,
					conversations: [],
					selectedConversationId: null,
					conversationLog: {
						messages: [],
						isLoading: false,
						error: null,
					},
				}));
			}
		}),
		vscode.workspace.onDidChangeTextDocument(async (event) => {
			await completeSlashCommandUseCase.execute(event);
		}),
	);

	void authService.getAuthState().then(async (state: AuthState) => {
		store.update((current) => ({
			...current,
			auth: state,
		}));
		if (state.isAuthenticated) {
			await refreshConversations();
		}
	});
}

async function runSignIn(
	authService: AuthService,
	viewProvider: ExplainCodeViewProvider,
): Promise<void> {
	try {
		await vscode.commands.executeCommand('workbench.view.extension.innomightlabs-code-assist-sidebar');
		viewProvider.showPendingAuthentication();
		await authService.startGoogleLogin();
	} catch (error) {
		viewProvider.clearPendingAuthentication();
		const message = error instanceof Error ? error.message : 'Unknown error';
		const configure = 'Configure Backend';
		const selected = await vscode.window.showErrorMessage(
			`Failed to start Google sign-in: ${message}`,
			configure,
		);
		if (selected === configure) {
			await vscode.commands.executeCommand(CONFIGURE_BACKEND_COMMAND);
		}
	}
}

async function runConfigureBackend(configService: ExtensionConfigService): Promise<void> {
	const config = await configService.configure();
	if (!config) {
		return;
	}
	void vscode.window.showInformationMessage('Innomightlabs backend configuration saved for this VS Code install.');
}

export function deactivate(): void {}
