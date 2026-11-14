import type { ConversationKind } from "../../../types/conversation";

/** The tabs of the conversations list, in order: what each is called, counts and says when it has nothing to show. */
export const CONVERSATION_KINDS: ReadonlyArray<{
  kind: ConversationKind;
  label: string;
  noun: string;
  empty: string;
}> = [
  { kind: "chat", label: "Chats", noun: "conversations", empty: "No conversations yet. Ask your first question below." },
  {
    kind: "automation",
    label: "Automations",
    noun: "automation runs",
    empty: "No automation runs yet. Each run's conversation appears here.",
  },
];

/** The tab named in the address (`?type=automation`), so a tab can be linked to; anything else is the chats. */
export function parseKind(param: string | null): ConversationKind {
  return CONVERSATION_KINDS.find((tab) => tab.kind === param)?.kind ?? "chat";
}

export function kindDetails(kind: ConversationKind) {
  return CONVERSATION_KINDS.find((tab) => tab.kind === kind) ?? CONVERSATION_KINDS[0];
}
