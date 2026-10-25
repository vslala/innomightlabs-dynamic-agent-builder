import { useRef } from "react";
import { Bot, Plus } from "lucide-react";
import { ChatComposer } from "../../../components/chat/ChatComposer";
import { TokenUsageIndicator } from "../../../components/chat/TokenUsageIndicator";
import { AttachmentChip } from "../../../components/chat/AttachmentChip";
import { Button } from "../../../components/ui/button";
import { FileInput } from "../../../components/ui/file-input";
import { PillSelect } from "../../../components/ui/pill-select";
import type { AgentResponse } from "../../../services/agents/AgentApiService";
import { CHAT_DOCUMENT_EXTENSIONS } from "../../../lib/documents";
import { ALLOWED_EXTENSIONS } from "../../../types/message";
import styles from "./ConversationStartComposer.module.css";

export type ConversationStartMode = "chat" | "image";

interface ConversationStartComposerProps {
  agents: AgentResponse[];
  selectedAgentId: string;
  prompt: string;
  /** Files picked before the conversation exists; the conversation page uploads them. */
  files: File[];
  mode: ConversationStartMode;
  debugEnabled: boolean;
  creating: boolean;
  error: string | null;
  /** Docked under the conversation cloud: just the composer, without the heading above it. */
  docked?: boolean;
  onAgentChange: (agentId: string) => void;
  onPromptChange: (value: string) => void;
  onFilesAdded: (files: File[]) => void;
  onFileRemoved: (file: File) => void;
  onModeChange: (mode: ConversationStartMode) => void;
  onDebugChange: (enabled: boolean) => void;
  onSubmit: () => void;
  onCreateAgent: () => void;
}

export function ConversationStartComposer({
  agents,
  selectedAgentId,
  prompt,
  files,
  mode,
  debugEnabled,
  creating,
  error,
  docked = false,
  onAgentChange,
  onPromptChange,
  onFilesAdded,
  onFileRemoved,
  onModeChange,
  onDebugChange,
  onSubmit,
  onCreateAgent,
}: ConversationStartComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const documentInputRef = useRef<HTMLInputElement>(null);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId);
  const supportsImage = selectedAgent?.capabilities?.includes("image_generation") ?? false;
  const agentOptions = agents.map((agent) => ({
    value: agent.agent_id,
    label: agent.agent_name,
    description: agent.agent_model || agent.agent_provider,
  }));

  if (agents.length === 0) {
    return (
      <section className={styles.emptySection}>
        <div>
          <h1 className={styles.emptyTitle}>Start a conversation</h1>
          <p className={styles.emptyDescription}>
            Create an agent before starting a conversation.
          </p>
        </div>
        <Button className={styles.createAgentButton} onClick={onCreateAgent}>
          <Plus className="h-4 w-4" />
          Create Agent
        </Button>
      </section>
    );
  }

  return (
    <section className={docked ? `${styles.section} ${styles.docked}` : styles.section}>
      {!docked && (
        <div className={styles.header}>
          <div className={styles.headerIcon}>
            <Bot className="h-5 w-5" />
          </div>
          <h1 className={styles.title}>
            Start a conversation
          </h1>
          <p className={styles.description}>
            Ask your first question, create an image, or continue an older chat from the conversation list.
          </p>
          {selectedAgent?.agent_description && (
            <p className={styles.agentDescription}>
              {selectedAgent.agent_description}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className={styles.errorBanner}>
          {error}
        </div>
      )}

      {files.length > 0 && (
        <div className={styles.attachments}>
          {files.map((file) => (
            <AttachmentChip
              key={`${file.name}-${file.size}-${file.lastModified}`}
              filename={file.name}
              size={file.size}
              onRemove={() => onFileRemoved(file)}
            />
          ))}
        </div>
      )}

      <FileInput
        ref={fileInputRef}
        multiple
        accept={[...ALLOWED_EXTENSIONS, "image/*"].join(",")}
        onChange={(event) => {
          if (event.target.files) onFilesAdded(Array.from(event.target.files));
          event.target.value = "";
        }}
      />
      <FileInput
        ref={documentInputRef}
        multiple
        accept={CHAT_DOCUMENT_EXTENSIONS.join(",")}
        onChange={(event) => {
          if (event.target.files) onFilesAdded(Array.from(event.target.files));
          event.target.value = "";
        }}
      />

      <ChatComposer
        value={prompt}
        disabled={creating}
        isSubmitting={creating}
        placeholder={mode === "image" ? "Describe the image you want" : "Ask anything"}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        onDropFiles={mode === "image" ? undefined : (data) => onFilesAdded(Array.from(data.files))}
        onAttachFiles={mode === "image" ? undefined : () => fileInputRef.current?.click()}
        onAttachDocuments={mode === "image" ? undefined : () => documentInputRef.current?.click()}
        statusIndicator={<TokenUsageIndicator agentId={selectedAgentId || undefined} />}
        imageAction={{
          active: mode === "image",
          disabled: !supportsImage,
          onClick: () => onModeChange(mode === "image" ? "chat" : "image"),
          title: supportsImage
            ? "Create an image"
            : "Selected agent does not support image generation",
        }}
        debugAction={{
          enabled: debugEnabled,
          disabled: mode === "image",
          onChange: onDebugChange,
        }}
        rightActions={
          <PillSelect
            value={selectedAgentId}
            options={agentOptions}
            placeholder="Select agent"
            onChange={onAgentChange}
          />
        }
      />
    </section>
  );
}
