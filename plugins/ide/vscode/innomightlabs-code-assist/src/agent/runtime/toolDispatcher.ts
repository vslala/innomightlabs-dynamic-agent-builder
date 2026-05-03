import type { ToolDefinition } from '../tools/toolDefinition';
import { validateJsonSchema } from '../tools/toolDefinition';

export type RuntimeToolCall = {
	callId: string;
	toolName: string;
	input: unknown;
};

export type RuntimeToolResult = {
	callId: string;
	toolName: string;
	output: unknown;
};

export interface RuntimeTool<TInput = unknown, TOutput = unknown> {
	name: string;
	execute(input: TInput): Promise<TOutput>;
}

export interface ToolDispatcher {
	dispatch(call: RuntimeToolCall): Promise<RuntimeToolResult>;
}

export class RegistryToolDispatcher implements ToolDispatcher {
	private readonly tools = new Map<string, ToolDefinition>();

	public constructor(tools: ToolDefinition[] = []) {
		for (const tool of tools) {
			this.tools.set(tool.name, tool);
		}
	}

	public async dispatch(call: RuntimeToolCall): Promise<RuntimeToolResult> {
		const tool = this.tools.get(call.toolName);
		if (!tool) {
			throw new Error(`Runtime tool not registered: ${call.toolName}`);
		}

		const schemaErrors = validateJsonSchema(call.input, tool.inputSchema);
		if (schemaErrors.length > 0) {
			throw new Error(`Invalid input for tool "${call.toolName}": ${schemaErrors.join(' ')}`);
		}

		const output = await tool.execute(call.input);
		return {
			callId: call.callId,
			toolName: call.toolName,
			output,
		};
	}
}
