import { useLayoutEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode, ClipboardEvent } from "react";
import { Image as ImageIcon, Loader2, Paperclip, SearchCheck, Send } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Toggle } from "../ui/toggle";
import styles from "./ChatComposer.module.css";

interface ComposerImageAction {
  active?: boolean;
  disabled?: boolean;
  visible?: boolean;
  title?: string;
  onClick: () => void;
}

interface ComposerDeepResearchAction {
  enabled: boolean;
  disabled?: boolean;
  visible?: boolean;
  onChange: (enabled: boolean) => void;
}

interface ChatComposerProps {
  value: string;
  placeholder?: string;
  disabled?: boolean;
  isSubmitting?: boolean;
  submitDisabled?: boolean;
  rightActions?: ReactNode;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onPaste?: (event: ClipboardEvent<HTMLTextAreaElement>) => void;
  onAttachFiles?: () => void;
  attachDisabled?: boolean;
  imageAction?: ComposerImageAction;
  deepResearchAction?: ComposerDeepResearchAction;
}

export function ChatComposer({
  value,
  placeholder = "Ask anything",
  disabled = false,
  isSubmitting = false,
  submitDisabled,
  rightActions,
  onChange,
  onSubmit,
  onPaste,
  onAttachFiles,
  attachDisabled = false,
  imageAction,
  deepResearchAction,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const showImageAction = imageAction?.visible ?? Boolean(imageAction);
  const showDeepResearch = deepResearchAction?.visible ?? Boolean(deepResearchAction);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [value]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className={styles.composer}>
      <div className={styles.composerInner}>
        <Textarea
          ref={textareaRef}
          value={value}
          rows={1}
          disabled={disabled || isSubmitting}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={onPaste}
          aria-busy={isSubmitting}
          className={styles.composerInput}
        />

        <div className={styles.composerControls}>
          <div className={styles.composerActions}>
            {onAttachFiles && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onAttachFiles}
                disabled={disabled || isSubmitting || attachDisabled}
                aria-label="Attach files"
                title="Attach files"
                className={styles.roundIconButton}
              >
                <Paperclip className={styles.buttonIcon} />
              </Button>
            )}

            {showImageAction && imageAction && (
              <Button
                type="button"
                variant={imageAction.active ? "default" : "ghost"}
                size="icon"
                onClick={imageAction.onClick}
                disabled={disabled || isSubmitting || imageAction.disabled}
                aria-label="Create an image"
                title={imageAction.title || "Create an image"}
                className={styles.roundIconButton}
              >
                <ImageIcon className={styles.buttonIcon} />
              </Button>
            )}

            {showDeepResearch && deepResearchAction && (
              <Toggle
                pressed={deepResearchAction.enabled}
                onPressedChange={deepResearchAction.onChange}
                disabled={disabled || isSubmitting || deepResearchAction.disabled}
                aria-label="Deep research"
                className={styles.researchToggle}
              >
                <SearchCheck className={styles.buttonIcon} />
                <span>Deep research</span>
              </Toggle>
            )}
          </div>

          <div className={styles.composerActions}>
            {rightActions && <div className={styles.rightActions}>{rightActions}</div>}
            <Button
              type="button"
              onClick={onSubmit}
              disabled={submitDisabled ?? (!value.trim() || disabled || isSubmitting)}
              className={styles.sendButton}
            >
              {isSubmitting ? (
                <Loader2 className={styles.sendSpinner} />
              ) : (
                <Send className={styles.buttonIcon} />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
