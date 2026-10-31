import { Bug, ChevronLeft, Maximize2, Minimize2, MoreVertical, Pencil, Trash2 } from "lucide-react";
import { Button } from "../../../../components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../../../../components/ui/dropdown-menu";
import styles from "./ConversationTopBar.module.css";

interface ConversationTopBarProps {
  title: string;
  agentName: string;
  description?: string | null;
  supportsImages: boolean;
  debugEnabled: boolean;
  /** Undefined where full screen means nothing, as on a phone, where the conversation already fills it. */
  expanded?: boolean;
  onBack: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onDebugChange: (enabled: boolean) => void;
  onExpandedChange?: (expanded: boolean) => void;
}

/** The conversation's one bar: back, what it is and who answers, and everything else behind a menu. */
export function ConversationTopBar({
  title,
  agentName,
  description,
  supportsImages,
  debugEnabled,
  expanded,
  onBack,
  onEdit,
  onDelete,
  onDebugChange,
  onExpandedChange,
}: ConversationTopBarProps) {
  return (
    <header className={styles.bar}>
      <Button variant="ghost" size="icon" onClick={onBack} aria-label="Back to conversations" className={styles.iconButton}>
        <ChevronLeft className={styles.backIcon} />
      </Button>

      <div className={styles.text} title={description || undefined}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.subtitle}>
          {agentName}
          {supportsImages && <span className={styles.badge}>Images</span>}
        </p>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Conversation options" className={styles.iconButton}>
            <MoreVertical className={styles.icon} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onEdit}>
            <Pencil />
            Edit details
          </DropdownMenuItem>
          <DropdownMenuCheckboxItem checked={debugEnabled} onCheckedChange={onDebugChange}>
            <Bug />
            Show tool details
          </DropdownMenuCheckboxItem>
          {expanded !== undefined && onExpandedChange && (
            <DropdownMenuItem onSelect={() => onExpandedChange(!expanded)}>
              {expanded ? <Minimize2 /> : <Maximize2 />}
              {expanded ? "Exit full screen" : "Full screen"}
            </DropdownMenuItem>
          )}
          <DropdownMenuSeparator />
          <DropdownMenuItem destructive onSelect={onDelete}>
            <Trash2 />
            Delete conversation
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
