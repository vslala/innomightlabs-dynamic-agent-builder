import { useLayoutEffect, useRef, useState } from "react";
import type { DragEvent, KeyboardEvent, ReactNode, ClipboardEvent } from "react";
import { Bug, FileUp, Image as ImageIcon, Loader2, Paperclip, Send, Square } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Toggle } from "../ui/toggle";
import { isFileDrag } from "../../../packages/image-attachments/src";
import styles from "./ChatComposer.module.css";

interface ComposerImageAction {
  active?: boolean;
  disabled?: boolean;
  visible?: boolean;
  title?: string;
  onClick: () => void;
}

interface ComposerDebugAction {
  enabled: boolean;
  disabled?: boolean;
  visible?: boolean;
  onChange: (enabled: boolean) => void;
}

interface ComposerStopAction {
  onStop: () => void;
  disabled?: boolean;
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
  /** Attach a document (PDF, Word…) to send with the message; the agent reads it with its document tools. */
  onAttachDocuments?: () => void;
  /** Files dropped on the composer. Setting it turns the composer into a drop target. */
  onDropFiles?: (data: DataTransfer) => void;
  imageAction?: ComposerImageAction;
  debugAction?: ComposerDebugAction;
  /** While submitting, replaces the send button with a stop affordance for the running turn. */
  stopAction?: ComposerStopAction;
  statusIndicator?: ReactNode;
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
  onAttachDocuments,
  onDropFiles,
  imageAction,
  debugAction,
  stopAction,
  statusIndicator,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [dragging, setDragging] = useState(false);
  const showImageAction = imageAction?.visible ?? Boolean(imageAction);
  const showDebug = debugAction?.visible ?? Boolean(debugAction);

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

  const dropEnabled = Boolean(onDropFiles) && !disabled && !isSubmitting;
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!dropEnabled || !isFileDrag(event.dataTransfer)) return;
    event.preventDefault();
    setDragging(true);
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!dropEnabled || !onDropFiles) return;
    event.preventDefault();
    setDragging(false);
    onDropFiles(event.dataTransfer);
  };

  return (
    <div className={styles.composer}>
      <div
        className={styles.composerInner}
        data-dragging={dragging || undefined}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
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

            {onAttachDocuments && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={onAttachDocuments}
                disabled={disabled || isSubmitting}
                aria-label="Attach a document"
                title="Attach a document (PDF, Word, slides, spreadsheet)"
                className={styles.roundIconButton}
              >
                <FileUp className={styles.buttonIcon} />
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

            {showDebug && debugAction && (
              <Toggle
                pressed={debugAction.enabled}
                onPressedChange={debugAction.onChange}
                disabled={disabled || debugAction.disabled}
                aria-label="Debug tool activity"
                title="Show tool arguments and results"
                className={styles.debugToggle}
              >
                <Bug className={styles.buttonIcon} />
                <span>Debug</span>
              </Toggle>
            )}

            {statusIndicator}
          </div>

          <div className={styles.composerActions}>
            {rightActions && <div className={styles.rightActions}>{rightActions}</div>}
            <Button
              type="button"
              onClick={isSubmitting && stopAction ? stopAction.onStop : onSubmit}
              disabled={
                isSubmitting
                  ? Boolean(stopAction?.disabled)
                  : (submitDisabled ?? (!value.trim() || disabled))
              }
              aria-label={isSubmitting && stopAction ? "Stop response" : "Send message"}
              title={isSubmitting && stopAction ? "Stop response" : undefined}
              className={styles.sendButton}
            >
              {isSubmitting ? (
                stopAction ? (
                  <Square className={styles.buttonIcon} />
                ) : (
                  <Loader2 className={styles.sendSpinner} />
                )
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
