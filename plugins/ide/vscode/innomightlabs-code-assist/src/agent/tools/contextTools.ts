import * as vscode from 'vscode';

import type { ToolDefinition } from './toolDefinition';

const DEFAULT_FILE_CHAR_LIMIT = 20000;
const DEFAULT_MAX_RESULTS = 25;

type ReadWorkspaceFileInput = {
	path: string;
	maxCharacters?: number;
};

type ListWorkspaceFilesInput = {
	glob?: string;
	maxResults?: number;
};

type SearchWorkspaceTextInput = {
	query: string;
	includePattern?: string;
	maxResults?: number;
};

export function createDefaultRuntimeTools(): ToolDefinition[] {
	return [
		{
			name: 'get_active_editor_context',
			description: 'Return the active editor file, language, cursor, selection, and truncated document text.',
			inputSchema: {
				type: 'object',
				description: 'No input is required for this tool.',
				properties: {},
				required: [],
				additionalProperties: false,
			},
			outputDescription: 'Current editor context including file, language, cursor, selection, and document text.',
			execute: async (): Promise<unknown> => {
				const editor = vscode.window.activeTextEditor;
				if (!editor) {
					return { available: false, reason: 'No active editor' };
				}

				const selection = editor.selection;
				const documentText = editor.document.getText();
				const maxCharacters = DEFAULT_FILE_CHAR_LIMIT;
				const truncatedText = documentText.slice(0, maxCharacters);

				return {
					available: true,
					fileName: editor.document.fileName,
					language: editor.document.languageId,
					cursor: {
						line: editor.selection.active.line,
						character: editor.selection.active.character,
					},
					selection: selection.isEmpty
						? null
						: {
							startLine: selection.start.line,
							startCharacter: selection.start.character,
							endLine: selection.end.line,
							endCharacter: selection.end.character,
							text: editor.document.getText(selection),
						},
					document: {
						text: truncatedText,
						isTruncated: documentText.length > maxCharacters,
						totalCharacters: documentText.length,
					},
				};
			},
		},
		{
			name: 'read_workspace_file',
			description: 'Read a workspace file by relative or absolute path.',
			inputSchema: {
				type: 'object',
				properties: {
					path: {
						type: 'string',
						description: 'Relative or absolute file path to read.',
					},
					maxCharacters: {
						type: 'number',
						description: 'Optional maximum number of characters to return.',
					},
				},
				required: ['path'],
				additionalProperties: false,
			},
			outputDescription: 'File path, file content, truncation flag, and total character count.',
			execute: async (input: ReadWorkspaceFileInput): Promise<unknown> => {
				const fileUri = resolveWorkspacePath(input.path);
				const bytes = await vscode.workspace.fs.readFile(fileUri);
				const text = new TextDecoder().decode(bytes);
				const maxCharacters = input.maxCharacters ?? DEFAULT_FILE_CHAR_LIMIT;

				return {
					path: vscode.workspace.asRelativePath(fileUri),
					content: text.slice(0, maxCharacters),
					isTruncated: text.length > maxCharacters,
					totalCharacters: text.length,
				};
			},
		},
		{
			name: 'list_workspace_files',
			description: 'List workspace files matching an optional glob pattern.',
			inputSchema: {
				type: 'object',
				properties: {
					glob: {
						type: 'string',
						description: 'Optional glob pattern, for example src/**/*.ts',
					},
					maxResults: {
						type: 'number',
						description: 'Optional maximum number of file paths to return.',
					},
				},
				required: [],
				additionalProperties: false,
			},
			outputDescription: 'List of matching workspace file paths and the number of results returned.',
			execute: async (input: ListWorkspaceFilesInput = {}): Promise<unknown> => {
				const maxResults = Math.min(input.maxResults ?? DEFAULT_MAX_RESULTS, 200);
				const files = await vscode.workspace.findFiles(
					input.glob ?? '**/*',
					'**/{node_modules,.git,dist,out,.vscode-test}/**',
					maxResults,
				);

				return {
					files: files.map((file) => vscode.workspace.asRelativePath(file)),
					count: files.length,
				};
			},
		},
		{
			name: 'search_workspace_text',
			description: 'Search for a plain text query across workspace files.',
			inputSchema: {
				type: 'object',
				properties: {
					query: {
						type: 'string',
						description: 'Plain text query to search for.',
					},
					includePattern: {
						type: 'string',
						description: 'Optional file glob used to limit which files are searched.',
					},
					maxResults: {
						type: 'number',
						description: 'Optional maximum number of matching lines to return.',
					},
				},
				required: ['query'],
				additionalProperties: false,
			},
			outputDescription: 'Matching file paths, line numbers, and preview lines for each text match.',
			execute: async (input: SearchWorkspaceTextInput): Promise<unknown> => {
				if (!input.query?.trim()) {
					return { matches: [], count: 0 };
				}

				const maxResults = Math.min(input.maxResults ?? DEFAULT_MAX_RESULTS, 100);
				const candidateFiles = await vscode.workspace.findFiles(
					input.includePattern ?? '**/*',
					'**/{node_modules,.git,dist,out,.vscode-test}/**',
					Math.min(maxResults * 3, 200),
				);
				const matches: Array<{
					path: string;
					line: number;
					preview: string;
				}> = [];

				for (const file of candidateFiles) {
					if (matches.length >= maxResults) {
						break;
					}

					const text = await readFileText(file);
					if (!text) {
						continue;
					}

					const lines = text.split('\n');
					for (let index = 0; index < lines.length; index += 1) {
						if (matches.length >= maxResults) {
							break;
						}

						if (lines[index].includes(input.query)) {
							matches.push({
								path: vscode.workspace.asRelativePath(file),
								line: index,
								preview: lines[index].trim(),
							});
						}
					}
				}

				return {
					matches,
					count: matches.length,
				};
			},
		},
	];
}

function resolveWorkspacePath(inputPath: string): vscode.Uri {
	const trimmedPath = inputPath.trim();
	if (!trimmedPath) {
		throw new Error('Tool input "path" must not be empty.');
	}

	const absolutePath = vscode.Uri.file(trimmedPath);
	if (vscode.workspace.getWorkspaceFolder(absolutePath)) {
		return absolutePath;
	}

	const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
	if (!workspaceFolder) {
		throw new Error('No workspace folder is open.');
	}

	return vscode.Uri.joinPath(workspaceFolder.uri, trimmedPath);
}

async function readFileText(file: vscode.Uri): Promise<string | null> {
	try {
		const bytes = await vscode.workspace.fs.readFile(file);
		return new TextDecoder().decode(bytes);
	} catch {
		return null;
	}
}
