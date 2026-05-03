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
	type RewriteSelectionResult,
	InnomightlabsClient,
} from '../../innomightlabsClient';
import type { ConversationStateSync, WorkflowViewPort } from './shared';

type RewriteSelectionUseCaseDependencies = {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: RewriteSelectionResult) => void;
};

export class RewriteSelectionUseCase {
	public constructor(private readonly dependencies: RewriteSelectionUseCaseDependencies) {}

	public async execute(): Promise<void> {
		const editor = vscode.window.activeTextEditor;
		if (!editor) {
			vscode.window.showErrorMessage('Open a file and select code to rewrite.');
			return;
		}

		const selection = editor.selection;
		if (selection.isEmpty) {
			vscode.window.showWarningMessage('Select the code you want to rewrite first.');
			return;
		}

		const selectedText = editor.document.getText(selection);
		if (!selectedText.trim()) {
			vscode.window.showWarningMessage('The current selection is empty.');
			return;
		}

		const instruction = await vscode.window.showInputBox({
			title: 'Rewrite Selected Code',
			prompt: 'Describe how the selected code should change',
			placeHolder: 'Example: refactor this to use async/await and add basic error handling',
			ignoreFocusOut: true,
			validateInput: (value: string) => {
				return value.trim().length === 0 ? 'Enter a rewrite instruction.' : null;
			},
		});
		if (!instruction) {
			return;
		}

		const context: RewriteSelectionPipelineContext = {
			client: this.dependencies.client,
			authService: this.dependencies.authService,
			view: this.dependencies.view,
			getSelectedConversationId: this.dependencies.getSelectedConversationId,
			syncConversationState: this.dependencies.syncConversationState,
			setLatestResult: this.dependencies.setLatestResult,
			editor,
			selection,
			instruction: instruction.trim(),
			selectedText,
			authenticationMode: 'interactive',
			unauthenticatedCode: selectedText,
			unauthenticatedLanguage: editor.document.languageId,
			unauthenticatedMessage: 'Sign in with Google before rewriting code.',
			workflowTitle: 'Rewriting selection',
			workflowSteps: [
				'Fetching agent configuration',
				'Loading conversations',
				'Preparing conversation',
				'Sending rewrite prompt',
				'Applying replacement',
			],
		};

		const pipeline = new Pipeline<RewriteSelectionPipelineContext>([
			openSidebarStep(),
			syncAuthStateStep(),
			requireAuthenticatedStep(),
			showWorkflowOverlayStep(),
			executeRewriteSelectionStep(),
			applyRewriteSelectionStep(),
			syncOperationResultStep<RewriteSelectionPipelineContext, RewriteSelectionResult>(),
		]);

		try {
			await pipeline.run(context);
		} catch (error) {
			const message = error instanceof Error ? error.message : 'Unknown error';
			vscode.window.showErrorMessage(`Rewrite selection failed: ${message}`);
		} finally {
			this.dependencies.view.hideWorkflowOverlay();
		}
	}
}

type RewriteSelectionPipelineContext = PipelineContext & {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: RewriteSelectionResult) => void;
	editor: vscode.TextEditor;
	selection: vscode.Selection;
	instruction: string;
	selectedText: string;
	authenticationMode: 'interactive';
	unauthenticatedCode: string;
	unauthenticatedLanguage: string;
	unauthenticatedMessage: string;
	workflowTitle: string;
	workflowSteps: string[];
	result?: RewriteSelectionResult;
};

function executeRewriteSelectionStep(): PipelineStep<RewriteSelectionPipelineContext> {
	return {
		async execute(context: RewriteSelectionPipelineContext): Promise<void> {
			context.result = await context.client.rewriteSelection(
				{
					documentText: context.editor.document.getText(),
					language: context.editor.document.languageId,
					fileName: context.editor.document.fileName,
					instruction: context.instruction,
					selectedText: context.selectedText,
					startLine: context.selection.start.line,
					startCharacter: context.selection.start.character,
					endLine: context.selection.end.line,
					endCharacter: context.selection.end.character,
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

function applyRewriteSelectionStep(): PipelineStep<RewriteSelectionPipelineContext> {
	return {
		async execute(context: RewriteSelectionPipelineContext): Promise<void> {
			if (!context.result) {
				return;
			}

			context.view.updateWorkflowStep('Applying replacement');
			await context.editor.edit((editBuilder) => {
				editBuilder.replace(context.selection, context.result?.replacement ?? '');
			});
		},
	};
}
