import type { ToolDefinition } from '../tools/toolDefinition';
import { renderSchema } from '../tools/toolDefinition';

export function buildToolProtocolInstructions(tools: ToolDefinition[]): string[] {
	return [
		'If you need more IDE or project context before answering, you may request one tool at a time.',
		'When requesting a tool, respond with only a JSON object in this shape:',
		'{"type":"tool_call","toolName":"tool_name_here","input":{}}',
		'Do not wrap the JSON in markdown fences.',
		'When you have enough context, return the final answer normally.',
		'Available tools:',
		...tools.flatMap((tool, index) => renderToolDefinition(tool, index + 1)),
	];
}

function renderToolDefinition(tool: ToolDefinition, index: number): string[] {
	return [
		`${index}. ${tool.name}`,
		`   Description: ${tool.description}`,
		'   Input schema:',
		...renderSchema(tool.inputSchema, 5),
		`   Output: ${tool.outputDescription}`,
		`   Example call: ${JSON.stringify(buildExampleCall(tool.name, tool.inputSchema))}`,
	];
}

function buildExampleCall(toolName: string, schema: ToolDefinition['inputSchema']): Record<string, unknown> {
	return {
		type: 'tool_call',
		toolName,
		input: buildExampleInput(schema),
	};
}

function buildExampleInput(schema: ToolDefinition['inputSchema']): unknown {
	if (schema.type !== 'object') {
		return {};
	}

	const input: Record<string, unknown> = {};
	for (const [key, property] of Object.entries(schema.properties)) {
		input[key] = exampleValueForSchema(property);
	}
	return input;
}

function exampleValueForSchema(schema: ToolDefinition['inputSchema']): unknown {
	switch (schema.type) {
		case 'string':
			return schema.description?.toLowerCase().includes('path') ? 'src/example.ts' : 'example';
		case 'number':
			return 25;
		case 'boolean':
			return true;
		case 'null':
			return null;
		case 'array':
			return [];
		case 'object':
			return buildExampleInput(schema);
	}
}
