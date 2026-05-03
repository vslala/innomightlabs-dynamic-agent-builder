import type { AuthState } from '../../auth/authService';
import type { ConversationSummary } from '../../innomightlabsClient';

export type ConversationStateSync = (
	conversations: ConversationSummary[],
	conversationId: string | null,
) => Promise<void>;

export interface WorkflowViewPort {
	setAuthState(auth: AuthState): void;
	showAuthenticationRequired(code: string, language: string): void;
	showWorkflowOverlay(title: string, steps: string[]): void;
	updateWorkflowStep(step: string): void;
	hideWorkflowOverlay(): void;
	showExplanation(input: { code: string; language: string; explanation: string }): void;
	showError(message: string, code: string, language: string): void;
}
