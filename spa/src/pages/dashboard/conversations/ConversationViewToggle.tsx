import { List, Orbit } from "lucide-react";
import { Tabs, TabsList, TabsTrigger } from "../../../components/ui/tabs";
import { parseView, type ConversationView } from "./conversationView";
import styles from "./ConversationViewToggle.module.css";

interface ConversationViewToggleProps {
  view: ConversationView;
  onChange: (view: ConversationView) => void;
}

/** Switches between the cloud and the classic list. */
export function ConversationViewToggle({ view, onChange }: ConversationViewToggleProps) {
  return (
    <Tabs value={view} onValueChange={(next) => onChange(parseView(next))}>
      <TabsList aria-label="Conversation view">
        <TabsTrigger value="cloud" className={styles.trigger}>
          <Orbit className="h-3.5 w-3.5" aria-hidden="true" /> Cloud
        </TabsTrigger>
        <TabsTrigger value="classic" className={styles.trigger}>
          <List className="h-3.5 w-3.5" aria-hidden="true" /> Classic
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}
