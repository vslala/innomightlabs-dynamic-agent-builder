import type { WidgetConversation } from '../../integrations/widget/widgetApiClient';

export type RuntimeStatusEvent = {
	type: 'status';
	step: string;
};

export type RuntimeToolCallRequestedEvent = {
	type: 'tool_call_requested';
	callId: string;
	toolName: string;
	input: unknown;
};

export type RuntimeToolResultReceivedEvent = {
	type: 'tool_result_received';
	callId: string;
	toolName: string;
	output: unknown;
};

export type RuntimeFinalTextEvent = {
	type: 'final_text';
	text: string;
};

export type RuntimeCompletedEvent = {
	type: 'completed';
	conversationId: string;
	conversations: WidgetConversation[];
	finalText: string;
};

export type RuntimeFailedEvent = {
	type: 'failed';
	message: string;
};

export type RuntimeEvent =
	| RuntimeStatusEvent
	| RuntimeToolCallRequestedEvent
	| RuntimeToolResultReceivedEvent
	| RuntimeFinalTextEvent
	| RuntimeCompletedEvent
	| RuntimeFailedEvent;
