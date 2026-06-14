import { useLayoutEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { Loader2, Send } from "lucide-react";
import { Button } from "./button";
import { cn } from "../../lib/utils";

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
      className={cn(
        "flex w-full items-end gap-3 rounded-[1.75rem] border border-[var(--border-subtle)] bg-white/[0.07] px-4 py-3 shadow-2xl shadow-black/20",
        className
      )}
    >
      {leftActions && <div className="flex shrink-0 items-end gap-2 pb-1">{leftActions}</div>}
      <textarea
        ref={textareaRef}
        value={value}
        rows={1}
        disabled={disabled || isSubmitting}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className="min-h-10 flex-1 resize-none overflow-y-auto bg-transparent px-0 py-2 text-base leading-6 text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] disabled:cursor-not-allowed disabled:opacity-60"
      />
      <div className="flex shrink-0 items-end gap-2 pb-1">
        {rightActions}
        <Button
          type="button"
          size="icon"
          className="h-10 w-10 rounded-full"
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

