import { Tabs, TabsList, TabsTrigger } from "../../../components/ui/tabs";
import type { ConversationKind } from "../../../types/conversation";
import { CONVERSATION_KINDS, parseKind } from "./conversationKind";

interface ConversationKindTabsProps {
  kind: ConversationKind;
  onChange: (kind: ConversationKind) => void;
}

/** Chats with agents, or the conversations automation runs leave behind. */
export function ConversationKindTabs({ kind, onChange }: ConversationKindTabsProps) {
  return (
    <Tabs value={kind} onValueChange={(value) => onChange(parseKind(value))}>
      <TabsList aria-label="Kind of conversation">
        {CONVERSATION_KINDS.map((tab) => (
          <TabsTrigger key={tab.kind} value={tab.kind}>
            {tab.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
