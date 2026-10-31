/** Below this width the sidebar is a drawer. Keep in step with the 900px rules in Sidebar.css and Header.css. */
export const COMPACT_QUERY = "(max-width: 900px)";

const CONVERSATION_THREAD_PATTERN = /^\/dashboard\/conversations\/[^/]+$/;

/** A single conversation: on compact screens it fills the screen with its own top bar, like a messaging app. */
export function isConversationThread(pathname: string): boolean {
  return CONVERSATION_THREAD_PATTERN.test(pathname);
}
