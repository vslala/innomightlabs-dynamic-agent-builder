import type { ConversationResponse } from "../types/conversation";

export function isAutomationConversation(conversation: ConversationResponse): boolean {
  return (
    conversation.conversation_type === "automation" ||
    Boolean(conversation.automation_id) ||
    Boolean(conversation.automation_run_id) ||
    conversation.title.startsWith("Automation Run:")
  );
}

export function userVisibleConversations(
  conversations: ConversationResponse[]
): ConversationResponse[] {
  return conversations.filter((conversation) => !isAutomationConversation(conversation));
}
