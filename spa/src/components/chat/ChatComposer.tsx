import { useLayoutEffect, useRef, useState } from "react";
import type { DragEvent, KeyboardEvent, ReactNode, ClipboardEvent } from "react";
import { Bug, FileUp, Image as ImageIcon, Loader2, Paperclip, Plus, Send, Square } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Toggle } from "../ui/toggle";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { isFileDrag } from "../../../packages/image-attachments/src";
import styles from "./ChatComposer.module.css";

/** Below this width the composer is one row, with its actions behind a "+" menu. Keep in step with ChatComposer.module.css. */
const PHONE_QUERY = "(max-width: 640px)";
/** Touch keyboards have no Shift+Enter, so there Enter is a new line and the send button sends. */
const TOUCH_QUERY = "(pointer: coarse)";
const MAX_INPUT_HEIGHT_PX = 160;
// Textarea sets its padding inline; these let the stylesheet choose it per breakpoint
const INPUT_PADDING = { paddingBlock: "var(--composer-input-py)", paddingInline: "var(--composer-input-px)" };

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
  /** Controls beside the send button, such as an agent picker. On a phone they sit above the input. */
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
  /** Secondary information such as token usage. Shown on wider screens only. */
  statusIndicator?: ReactNode;
  /** Chips for what will be sent with the message, shown inside the composer above the input. */
  attachments?: ReactNode;
  /** A message under the composer, such as an attachment error. */
  notice?: ReactNode;
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
  attachments,
  notice,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [dragging, setDragging] = useState(false);
  const phone = useMediaQuery(PHONE_QUERY);
  const showImageAction = (imageAction?.visible ?? Boolean(imageAction)) && imageAction ? imageAction : null;
  const showDebug = (debugAction?.visible ?? Boolean(debugAction)) && debugAction ? debugAction : null;
  const busy = disabled || isSubmitting;
  const stopping = isSubmitting && stopAction;

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, MAX_INPUT_HEIGHT_PX)}px`;
  }, [value]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    if (window.matchMedia(TOUCH_QUERY).matches) return;
    event.preventDefault();
    onSubmit();
  };

  const dropEnabled = Boolean(onDropFiles) && !busy;
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

  const sendButton = (
    <Button
      type="button"
      size="icon"
      onClick={stopping ? stopAction.onStop : onSubmit}
      disabled={isSubmitting ? Boolean(stopAction?.disabled) : (submitDisabled ?? (!value.trim() || disabled))}
      aria-label={stopping ? "Stop response" : "Send message"}
      title={stopping ? "Stop response" : "Send message"}
      className={styles.sendButton}
    >
      {isSubmitting ? (
        stopAction ? <Square className={styles.buttonIcon} /> : <Loader2 className={styles.sendSpinner} />
      ) : (
        <Send className={styles.buttonIcon} />
      )}
    </Button>
  );

  const input = (
    <Textarea
      ref={textareaRef}
      value={value}
      rows={1}
      disabled={busy}
      placeholder={placeholder}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={handleKeyDown}
      onPaste={onPaste}
      aria-label={placeholder}
      aria-busy={isSubmitting}
      className={styles.composerInput}
      style={INPUT_PADDING}
    />
  );

  const hasMenuActions = Boolean(onAttachFiles || onAttachDocuments || showImageAction || showDebug);

  return (
    <div className={styles.composer}>
      <div
        className={styles.composerInner}
        data-dragging={dragging || undefined}
        onDragOver={handleDragOver}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        {attachments && <div className={styles.attachments}>{attachments}</div>}

        {phone ? (
          <>
            {rightActions && <div className={styles.phoneTopRow}>{rightActions}</div>}
            <div className={styles.phoneRow}>
              {hasMenuActions && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      disabled={busy}
                      aria-label="Add files and more"
                      className={styles.roundIconButton}
                    >
                      <Plus className={styles.buttonIcon} />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent side="top" align="start">
                    {onAttachFiles && (
                      <DropdownMenuItem disabled={attachDisabled} onSelect={onAttachFiles}>
                        <Paperclip />
                        Photos and files
                      </DropdownMenuItem>
                    )}
                    {onAttachDocuments && (
                      <DropdownMenuItem onSelect={onAttachDocuments}>
                        <FileUp />
                        Document (PDF, Word, slides)
                      </DropdownMenuItem>
                    )}
                    {showImageAction && (
                      <DropdownMenuItem disabled={showImageAction.disabled} onSelect={showImageAction.onClick}>
                        <ImageIcon />
                        {showImageAction.active ? "Back to chat" : "Create an image"}
                      </DropdownMenuItem>
                    )}
                    {showDebug && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuCheckboxItem
                          checked={showDebug.enabled}
                          disabled={showDebug.disabled}
                          onCheckedChange={showDebug.onChange}
                        >
                          <Bug />
                          Show tool details
                        </DropdownMenuCheckboxItem>
                      </>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
              {input}
              {sendButton}
            </div>
          </>
        ) : (
          <>
            {input}
            <div className={styles.composerControls}>
              <div className={styles.composerActions}>
                {onAttachFiles && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={onAttachFiles}
                    disabled={busy || attachDisabled}
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
                    disabled={busy}
                    aria-label="Attach a document"
                    title="Attach a document (PDF, Word, slides, spreadsheet)"
                    className={styles.roundIconButton}
                  >
                    <FileUp className={styles.buttonIcon} />
                  </Button>
                )}

                {showImageAction && (
                  <Button
                    type="button"
                    variant={showImageAction.active ? "default" : "ghost"}
                    size="icon"
                    onClick={showImageAction.onClick}
                    disabled={busy || showImageAction.disabled}
                    aria-label="Create an image"
                    title={showImageAction.title || "Create an image"}
                    className={styles.roundIconButton}
                  >
                    <ImageIcon className={styles.buttonIcon} />
                  </Button>
                )}

                {showDebug && (
                  <Toggle
                    pressed={showDebug.enabled}
                    onPressedChange={showDebug.onChange}
                    disabled={disabled || showDebug.disabled}
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
                {sendButton}
              </div>
            </div>
          </>
        )}
      </div>
      {notice && <div className={styles.notice}>{notice}</div>}
    </div>
  );
}
