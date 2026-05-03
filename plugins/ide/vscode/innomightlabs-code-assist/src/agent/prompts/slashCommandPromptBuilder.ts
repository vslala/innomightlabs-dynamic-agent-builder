import { buildToolProtocolInstructions } from './toolProtocol';
import type { ToolDefinition } from '../tools/toolDefinition';

export type SlashCommandPromptRequest = {
	documentText: string;
	language: string;
	fileName: string;
	command: string;
	lineNumber: number;
};

export type SlashCommandPromptContext = {
	agentName: string;
	tools: ToolDefinition[];
};

export class SlashCommandPromptBuilder {
	public build(request: SlashCommandPromptRequest, context: SlashCommandPromptContext): string {
		return [
			'You are helping inside a VS Code extension.',
			'The user typed a slash command requesting an in-place code completion or transformation.',
			'Return only the code to insert at the command location.',
			'Do not include markdown fences, explanations, or surrounding commentary.',
			'Match the file language and preserve the local coding style and indentation.',
			...buildToolProtocolInstructions(context.tools),
			'',
			'IDE context:',
			`- Agent name: ${context.agentName}`,
			`- File: ${request.fileName}`,
			`- Language: ${request.language}`,
			`- Slash command line: ${request.lineNumber + 1}`,
			'',
			'User slash command:',
			request.command,
			'',
			'Document content:',
			'```',
			this.injectCursorMarker(request.documentText, request.lineNumber),
			'```',
		].join('\n');
	}

	private injectCursorMarker(documentText: string, lineNumber: number): string {
		const lines = documentText.split('\n');
		if (lineNumber >= 0 && lineNumber < lines.length) {
			lines[lineNumber] = `/* CURSOR COMMAND LINE */\n${lines[lineNumber]}`;
		}
		return lines.join('\n');
	}
}
