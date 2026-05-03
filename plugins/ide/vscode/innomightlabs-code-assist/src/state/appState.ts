import type { AuthState } from '../auth/authService';
import type { ConversationMessage, ConversationSummary } from '../innomightlabsClient';

export type ExplainPanelState = {
	code: string;
	language: string;
	explanation: string;
	status: 'idle' | 'ready' | 'error';
};

export type WorkflowState = {
	visible: boolean;
	title: string;
	steps: string[];
	currentStep: string | null;
};

export type ConversationLogState = {
	messages: ConversationMessage[];
	isLoading: boolean;
	error: string | null;
};

export type AppState = {
	auth: AuthState;
	conversations: ConversationSummary[];
	selectedConversationId: string | null;
	explainPanel: ExplainPanelState;
	workflow: WorkflowState;
	conversationLog: ConversationLogState;
};

export const initialAppState: AppState = {
	auth: {
		isAuthenticated: false,
		isAuthenticating: false,
		visitor: null,
	},
	conversations: [],
	selectedConversationId: null,
	explainPanel: {
		code: '',
		language: '',
		explanation: 'Select a code snippet, right-click, and run Explain Code.',
		status: 'idle',
	},
	workflow: {
		visible: false,
		title: '',
		steps: [],
		currentStep: null,
	},
	conversationLog: {
		messages: [],
		isLoading: false,
		error: null,
	},
};
