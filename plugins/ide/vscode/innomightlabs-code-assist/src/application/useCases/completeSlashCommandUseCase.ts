import * as vscode from 'vscode';

import { Pipeline, type PipelineContext, type PipelineStep } from '../pipelines/pipeline';
import {
	requireAuthenticatedStep,
	showWorkflowOverlayStep,
	syncAuthStateStep,
	syncOperationResultStep,
} from '../pipelines/workflowSteps';
import { AuthService } from '../../auth/authService';
import {
	type SlashCommandResult,
	InnomightlabsClient,
} from '../../innomightlabsClient';
import type { ConversationStateSync, WorkflowViewPort } from './shared';

type CompleteSlashCommandUseCaseDependencies = {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: SlashCommandResult) => void;
};

export class CompleteSlashCommandUseCase {
	private readonly documentsUnderEdit = new Set<string>();

	public constructor(private readonly dependencies: CompleteSlashCommandUseCaseDependencies) {}

	public async execute(event: vscode.TextDocumentChangeEvent): Promise<void> {
		const documentKey = event.document.uri.toString();
		if (event.document.isClosed || this.documentsUnderEdit.has(documentKey)) {
			return;
		}

		const editor = vscode.window.activeTextEditor;
		if (!editor || editor.document.uri.toString() !== documentKey) {
			return;
		}

		const newlineChange = event.contentChanges.find((change) => change.text.includes('\n'));
		if (!newlineChange) {
			return;
		}

		const commandLine = newlineChange.range.start.line;
		if (commandLine < 0 || commandLine >= event.document.lineCount) {
			return;
		}

		const commandLineText = event.document.lineAt(commandLine).text;
		const trimmedCommandLine = commandLineText.trim();
		if (!trimmedCommandLine.startsWith('/') || trimmedCommandLine.length <= 1) {
			return;
		}

		const authState = await this.dependencies.authService.getAuthState();
		if (!authState.isAuthenticated) {
			return;
		}

		const command = trimmedCommandLine.slice(1).trim();
		if (!command) {
			return;
		}

		const nextLineStart = commandLine + 1 < event.document.lineCount
			? new vscode.Position(commandLine + 1, 0)
			: event.document.lineAt(commandLine).range.end;
		const replaceRange = new vscode.Range(
			new vscode.Position(commandLine, 0),
			nextLineStart,
		);
		const indentation = commandLineText.match(/^\s*/)?.[0] ?? '';

		const context: CompleteSlashCommandPipelineContext = {
			client: this.dependencies.client,
			authService: this.dependencies.authService,
			view: this.dependencies.view,
			getSelectedConversationId: this.dependencies.getSelectedConversationId,
			syncConversationState: this.dependencies.syncConversationState,
			setLatestResult: this.dependencies.setLatestResult,
			editor,
			event,
			documentKey,
			command,
			commandLine,
			indentation,
			replaceRange,
			authenticationMode: 'silent',
			unauthenticatedCode: '',
			unauthenticatedLanguage: event.document.languageId,
			workflowTitle: 'Generating code',
			workflowSteps: [
				'Fetching agent configuration',
				'Loading conversations',
				'Preparing conversation',
				'Sending code completion prompt',
				'Finalizing response',
			],
		};

		const pipeline = new Pipeline<CompleteSlashCommandPipelineContext>([
			syncAuthStateStep(),
			requireAuthenticatedStep(),
			showWorkflowOverlayStep(),
			executeSlashCommandStep(),
			applySlashCommandResultStep(this.documentsUnderEdit),
			syncOperationResultStep<CompleteSlashCommandPipelineContext, SlashCommandResult>(),
		]);

		try {
			await pipeline.run(context);
		} catch (error) {
			const message = error instanceof Error ? error.message : 'Unknown error';
			vscode.window.showErrorMessage(`Slash command failed: ${message}`);
		} finally {
			this.dependencies.view.hideWorkflowOverlay();
			queueMicrotask(() => {
				this.documentsUnderEdit.delete(documentKey);
			});
		}
	}
}

type CompleteSlashCommandPipelineContext = PipelineContext & {
	client: InnomightlabsClient;
	authService: AuthService;
	view: WorkflowViewPort;
	getSelectedConversationId: () => string | null;
	syncConversationState: ConversationStateSync;
	setLatestResult: (result: SlashCommandResult) => void;
	editor: vscode.TextEditor;
	event: vscode.TextDocumentChangeEvent;
	documentKey: string;
	command: string;
	commandLine: number;
	indentation: string;
	replaceRange: vscode.Range;
	authenticationMode: 'silent';
	unauthenticatedCode: string;
	unauthenticatedLanguage: string;
	workflowTitle: string;
	workflowSteps: string[];
	result?: SlashCommandResult;
};

function executeSlashCommandStep(): PipelineStep<CompleteSlashCommandPipelineContext> {
	return {
		async execute(context: CompleteSlashCommandPipelineContext): Promise<void> {
			context.result = await context.client.completeSlashCommand(
				{
					documentText: context.event.document.getText(),
					language: context.event.document.languageId,
					fileName: context.event.document.fileName,
					command: context.command,
					lineNumber: context.commandLine,
					indentation: context.indentation,
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

function applySlashCommandResultStep(
	documentsUnderEdit: Set<string>,
): PipelineStep<CompleteSlashCommandPipelineContext> {
	return {
		async execute(context: CompleteSlashCommandPipelineContext): Promise<void> {
			if (!context.result) {
				return;
			}

			const replacement = applyIndentation(context.result.completion, context.indentation);
			documentsUnderEdit.add(context.documentKey);
			await context.editor.edit((editBuilder) => {
				editBuilder.replace(context.replaceRange, replacement);
			});
		},
	};
}

function applyIndentation(completion: string, indentation: string): string {
	return completion
		.replace(/\r\n/g, '\n')
		.split('\n')
		.map((line) => `${indentation}${line}`)
		.join('\n');
}
