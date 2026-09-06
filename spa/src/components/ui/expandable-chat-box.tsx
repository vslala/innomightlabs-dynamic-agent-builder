import { useLayoutEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "./button";
import { cn } from "../../lib/utils";
import styles from "./expandable-chat-box.module.css";

interface ExpandableChatBoxProps {
  value: string;
  placeholder?: string;
  isSubmitting?: boolean;
  disabled?: boolean;
  leftActions?: ReactNode;
  rightActions?: ReactNode;
  className?: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function ExpandableChatBox({
  value,
  placeholder = "Ask anything",
  isSubmitting = false,
  disabled = false,
  leftActions,
  rightActions,
  className,
  onChange,
  onSubmit,
}: ExpandableChatBoxProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 224)}px`;
  }, [value]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <div
      className={cn(styles.container, className)}
    >
      {leftActions && <div className={styles.actionsRow}>{leftActions}</div>}
      <textarea
        ref={textareaRef}
        value={value}
        rows={1}
        disabled={disabled || isSubmitting}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className={styles.textarea}
      />
      <div className={styles.actionsRow}>
        {rightActions}
        <Button
          type="button"
          size="icon"
          className={styles.sendButton}
          disabled={!value.trim() || disabled || isSubmitting}
          onClick={onSubmit}
        >
          {isSubmitting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
}
