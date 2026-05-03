import * as vscode from 'vscode';

import type { AuthService, AuthState } from '../../auth/authService';
import type { ConversationSummary } from '../../innomightlabsClient';
import type { ConversationStateSync, WorkflowViewPort } from '../useCases/shared';
import type { PipelineContext, PipelineStep } from './pipeline';

type AuthAwareContext = PipelineContext & {
	authService: AuthService;
	view: WorkflowViewPort;
	authState?: AuthState;
};

type RequiresAuthenticationContext = AuthAwareContext & {
	authenticationMode: 'interactive' | 'silent';
	unauthenticatedCode: string;
	unauthenticatedLanguage: string;
	unauthenticatedMessage?: string;
};

type WorkflowOverlayContext = PipelineContext & {
	view: WorkflowViewPort;
	workflowTitle: string;
	workflowSteps: string[];
};

type OperationResult = {
	conversations: ConversationSummary[];
	conversationId: string;
};

type ResultAwareContext<TResult extends OperationResult> = PipelineContext & {
	result?: TResult;
	setLatestResult: (result: TResult) => void;
	syncConversationState: ConversationStateSync;
};

export function openSidebarStep<TContext extends PipelineContext>(): PipelineStep<TContext> {
	return {
		async execute(): Promise<void> {
			await vscode.commands.executeCommand('workbench.view.extension.innomightlabs-code-assist-sidebar');
		},
	};
}

export function syncAuthStateStep<TContext extends AuthAwareContext>(): PipelineStep<TContext> {
	return {
		async execute(context: TContext): Promise<void> {
			context.authState = await context.authService.getAuthState();
			context.view.setAuthState(context.authState);
		},
	};
}

export function requireAuthenticatedStep<TContext extends RequiresAuthenticationContext>(): PipelineStep<TContext> {
	return {
		async execute(context: TContext): Promise<void> {
			if (context.authState?.isAuthenticated) {
				return;
			}

			if (context.authenticationMode === 'interactive') {
				context.view.showAuthenticationRequired(
					context.unauthenticatedCode,
					context.unauthenticatedLanguage,
				);
				vscode.window.showInformationMessage(
					context.unauthenticatedMessage ?? 'Sign in with Google before continuing.',
				);
			}

			context.halted = true;
		},
	};
}

export function showWorkflowOverlayStep<TContext extends WorkflowOverlayContext>(): PipelineStep<TContext> {
	return {
		async execute(context: TContext): Promise<void> {
			context.view.showWorkflowOverlay(context.workflowTitle, context.workflowSteps);
		},
	};
}

export function syncOperationResultStep<
	TContext extends ResultAwareContext<TResult>,
	TResult extends OperationResult,
>(): PipelineStep<TContext> {
	return {
		async execute(context: TContext): Promise<void> {
			if (!context.result) {
				return;
			}

			context.setLatestResult(context.result);
			await context.syncConversationState(
				context.result.conversations,
				context.result.conversationId,
			);
		},
	};
}
