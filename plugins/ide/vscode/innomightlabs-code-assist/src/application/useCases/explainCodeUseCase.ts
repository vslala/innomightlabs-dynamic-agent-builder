import * as vscode from 'vscode';

import { Pipeline, type PipelineContext, type PipelineStep } from '../pipelines/pipeline';
import {
	openSidebarStep,
	requireAuthenticatedStep,
	showWorkflowOverlayStep,
	syncAuthStateStep,
	syncOperationResultStep,
} from '../pipelines/workflowSteps';
import { AuthService } from '../../auth/authService';
import {
	type ExplainCodeResult,
	InnomightlabsClient,
} from '../../innomightlabsClient';
import type { ConversationStateSync, WorkflowViewPort } from './shared';

type ExplainCodeUseCaseDependencies = {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: ExplainCodeResult) => void;
};

export class ExplainCodeUseCase {
	public constructor(private readonly dependencies: ExplainCodeUseCaseDependencies) {}

	public async execute(): Promise<void> {
		const editor = vscode.window.activeTextEditor;
		if (!editor) {
			vscode.window.showErrorMessage('Open a file and select code to explain.');
			return;
		}

		const selection = editor.selection;
		if (selection.isEmpty) {
			vscode.window.showWarningMessage('Select a code snippet first.');
			return;
		}

		const selectedCode = editor.document.getText(selection).trim();
		if (!selectedCode) {
			vscode.window.showWarningMessage('The current selection is empty.');
			return;
		}

		const userQuestion = await vscode.window.showInputBox({
			title: 'Ask About Selected Code',
			prompt: 'What do you want to know about the selected code?',
			placeHolder: 'Example: explain the control flow and any edge cases',
			ignoreFocusOut: true,
			validateInput: (value: string) => {
				return value.trim().length === 0 ? 'Enter a question about the selected code.' : null;
			},
		});
		if (!userQuestion) {
			return;
		}

		const context: ExplainCodePipelineContext = {
			client: this.dependencies.client,
			authService: this.dependencies.authService,
			view: this.dependencies.view,
			getSelectedConversationId: this.dependencies.getSelectedConversationId,
			syncConversationState: this.dependencies.syncConversationState,
			setLatestResult: this.dependencies.setLatestResult,
			code: selectedCode,
			language: editor.document.languageId,
			fileName: editor.document.fileName,
			userQuestion: userQuestion.trim(),
			authenticationMode: 'interactive',
			unauthenticatedCode: selectedCode,
			unauthenticatedLanguage: editor.document.languageId,
			unauthenticatedMessage: 'Sign in with Google before using Explain Code.',
			workflowTitle: 'Explaining code',
			workflowSteps: [
				'Fetching agent configuration',
				'Loading conversations',
				'Preparing conversation',
				'Sending explain prompt',
				'Finalizing response',
			],
		};

		const pipeline = new Pipeline<ExplainCodePipelineContext>([
			openSidebarStep(),
			syncAuthStateStep(),
			requireAuthenticatedStep(),
			showWorkflowOverlayStep(),
			executeExplainCodeStep(),
			syncOperationResultStep<ExplainCodePipelineContext, ExplainCodeResult>(),
			publishExplainResultStep(),
		]);

		try {
			await pipeline.run(context);
		} catch (error) {
			const message = error instanceof Error ? error.message : 'Unknown error';
			this.dependencies.view.showError(message, selectedCode, context.language);
			vscode.window.showErrorMessage(`Failed to explain code: ${message}`);
		} finally {
			this.dependencies.view.hideWorkflowOverlay();
		}
	}
}

type ExplainCodePipelineContext = PipelineContext & {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: ExplainCodeResult) => void;
	code: string;
	language: string;
	fileName: string;
	userQuestion: string;
	authenticationMode: 'interactive';
	unauthenticatedCode: string;
	unauthenticatedLanguage: string;
	unauthenticatedMessage: string;
	workflowTitle: string;
	workflowSteps: string[];
	result?: ExplainCodeResult;
};

function executeExplainCodeStep(): PipelineStep<ExplainCodePipelineContext> {
	return {
		async execute(context: ExplainCodePipelineContext): Promise<void> {
			context.result = await context.client.explainCode(
				{
					code: context.code,
					language: context.language,
					fileName: context.fileName,
					userQuestion: context.userQuestion,
				},
				{
					conversationId: context.getSelectedConversationId(),
					onProgress: (step: string) => {
						context.view.updateWorkflowStep(step);
					},
				},
			);
		},
	};
}

function publishExplainResultStep(): PipelineStep<ExplainCodePipelineContext> {
	return {
		async execute(context: ExplainCodePipelineContext): Promise<void> {
			if (!context.result) {
				return;
			}

			context.view.showExplanation({
				code: context.code,
				language: context.language,
				explanation: context.result.explanation,
			});
		},
	};
}
