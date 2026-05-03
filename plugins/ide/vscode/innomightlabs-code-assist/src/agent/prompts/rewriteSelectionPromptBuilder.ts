import { buildToolProtocolInstructions } from './toolProtocol';
import type { ToolDefinition } from '../tools/toolDefinition';

export type RewriteSelectionPromptRequest = {
	documentText: string;
	language: string;
	fileName: string;
	instruction: string;
	selectedText: string;
	startLine: number;
	startCharacter: number;
	endLine: number;
	endCharacter: number;
};

export type RewriteSelectionPromptContext = {
	agentName: string;
	tools: ToolDefinition[];
};

export class RewriteSelectionPromptBuilder {
	public build(request: RewriteSelectionPromptRequest, context: RewriteSelectionPromptContext): string {
		return [
			'You are helping inside a VS Code extension.',
			'The user selected an existing code range and wants that exact range rewritten in place.',
			'Return only the replacement code for the selected range.',
			'Do not include markdown fences, explanations, bullet points, or surrounding file content.',
			'Preserve the file language, local coding style, and any required indentation inside the selected range.',
			'If the selected range should be removed, return an empty string.',
			...buildToolProtocolInstructions(context.tools),
			'',
			'IDE context:',
			`- Agent name: ${context.agentName}`,
			`- File: ${request.fileName}`,
			`- Language: ${request.language}`,
			`- Selection start: line ${request.startLine + 1}, column ${request.startCharacter + 1}`,
			`- Selection end: line ${request.endLine + 1}, column ${request.endCharacter + 1}`,
			`- Selected characters: ${request.selectedText.length}`,
			'',
			'User instruction:',
			request.instruction,
			'',
			'Selected code to replace:',
			'```',
			request.selectedText,
			'```',
			'',
			'Full document with selection markers:',
			'```',
			this.injectSelectionMarkers(request),
			'```',
		].join('\n');
	}

	private injectSelectionMarkers(request: RewriteSelectionPromptRequest): string {
		const lines = request.documentText.split('\n');
		if (lines.length === 0) {
			return '';
		}

		const startLine = Math.min(Math.max(request.startLine, 0), lines.length - 1);
		const endLine = Math.min(Math.max(request.endLine, startLine), lines.length - 1);
		const startCharacter = Math.min(Math.max(request.startCharacter, 0), lines[startLine].length);
		const endCharacter = Math.min(Math.max(request.endCharacter, 0), lines[endLine].length);

		if (startLine === endLine) {
			const line = lines[startLine];
			lines[startLine] = [
				line.slice(0, startCharacter),
				'/* SELECTION START */',
				line.slice(startCharacter, endCharacter),
				'/* SELECTION END */',
				line.slice(endCharacter),
			].join('');
			return lines.join('\n');
		}

		lines[startLine] = [
			lines[startLine].slice(0, startCharacter),
			'/* SELECTION START */',
			lines[startLine].slice(startCharacter),
		].join('');
		lines[endLine] = [
			lines[endLine].slice(0, endCharacter),
			'/* SELECTION END */',
			lines[endLine].slice(endCharacter),
		].join('');
		return lines.join('\n');
	}
}
