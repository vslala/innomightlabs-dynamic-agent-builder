import { createDefaultRuntimeTools } from './contextTools';
import type { ToolDefinition } from './toolDefinition';

export function createDefaultToolRegistry(): ToolDefinition[] {
	return createDefaultRuntimeTools();
}
