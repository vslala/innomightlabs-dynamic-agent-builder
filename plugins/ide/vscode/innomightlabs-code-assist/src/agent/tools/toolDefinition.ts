export type JsonSchema =
	| {
		type: 'object';
		description?: string;
		properties: Record<string, JsonSchema>;
		required?: string[];
		additionalProperties?: boolean;
	}
	| {
		type: 'string' | 'number' | 'boolean';
		description?: string;
	}
	| {
		type: 'array';
		description?: string;
		items: JsonSchema;
	}
	| {
		type: 'null';
		description?: string;
	};

export interface ToolDefinition<TInput = unknown, TOutput = unknown> {
	name: string;
	description: string;
	inputSchema: JsonSchema;
	outputDescription: string;
	execute(input: TInput): Promise<TOutput>;
}

export function validateJsonSchema(value: unknown, schema: JsonSchema, path = 'input'): string[] {
	switch (schema.type) {
		case 'string':
			return typeof value === 'string' ? [] : [`${path} must be a string.`];
		case 'number':
			return typeof value === 'number' ? [] : [`${path} must be a number.`];
		case 'boolean':
			return typeof value === 'boolean' ? [] : [`${path} must be a boolean.`];
		case 'null':
			return value === null ? [] : [`${path} must be null.`];
		case 'array':
			if (!Array.isArray(value)) {
				return [`${path} must be an array.`];
			}
			return value.flatMap((item, index) => validateJsonSchema(item, schema.items, `${path}[${index}]`));
		case 'object':
			if (!isRecord(value)) {
				return [`${path} must be an object.`];
			}

			const errors: string[] = [];
			const required = schema.required ?? [];
			for (const key of required) {
				if (!(key in value)) {
					errors.push(`${path}.${key} is required.`);
				}
			}

			for (const [key, propertySchema] of Object.entries(schema.properties)) {
				if (!(key in value)) {
					continue;
				}
				errors.push(...validateJsonSchema(value[key], propertySchema, `${path}.${key}`));
			}

			if (schema.additionalProperties === false) {
				for (const key of Object.keys(value)) {
					if (!(key in schema.properties)) {
						errors.push(`${path}.${key} is not allowed.`);
					}
				}
			}

			return errors;
	}
}

export function renderSchema(schema: JsonSchema, indent = 0): string[] {
	const pad = ' '.repeat(indent);
	switch (schema.type) {
		case 'string':
		case 'number':
		case 'boolean':
		case 'null':
			return [`${pad}${schema.type}${schema.description ? ` - ${schema.description}` : ''}`];
		case 'array':
			return [
				`${pad}array${schema.description ? ` - ${schema.description}` : ''}`,
				`${pad}items:`,
				...renderSchema(schema.items, indent + 2),
			];
		case 'object': {
			const required = new Set(schema.required ?? []);
			const lines = [`${pad}object${schema.description ? ` - ${schema.description}` : ''}`];
			for (const [key, property] of Object.entries(schema.properties)) {
				lines.push(`${pad}${key}${required.has(key) ? ' (required)' : ' (optional)'}:`);
				lines.push(...renderSchema(property, indent + 2));
			}
			return lines;
		}
	}
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === 'object' && !Array.isArray(value);
}
