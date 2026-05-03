import { buildToolProtocolInstructions } from './toolProtocol';
import type { ToolDefinition } from '../tools/toolDefinition';

export type ExplainPromptRequest = {
	code: string;
	language: string;
	fileName: string;
	userQuestion: string;
};

export type ExplainPromptContext = {
	agentName: string;
	tools: ToolDefinition[];
};

export class ExplainPromptBuilder {
	public build(request: ExplainPromptRequest, context: ExplainPromptContext): string {
		return [
			'You are helping inside a VS Code extension.',
			'Answer the user’s question about the selected code.',
			'Focus on the specific thing they asked, but include important control flow, inputs/outputs, and notable risks when relevant.',
			'Keep the answer concise but useful.',
			...buildToolProtocolInstructions(context.tools),
			'',
			'User question:',
			request.userQuestion,
			'',
			'IDE context:',
			`- Agent name: ${context.agentName}`,
			`- File: ${request.fileName}`,
			`- Language: ${request.language}`,
			`- Selected characters: ${request.code.length}`,
			'',
			'Selected code:',
			'```',
			request.code,
			'```',
		].join('\n');
	}
}
