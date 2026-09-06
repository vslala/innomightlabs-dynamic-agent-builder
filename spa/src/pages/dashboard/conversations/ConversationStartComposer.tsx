import { Bot, Plus } from "lucide-react";
import { ChatComposer } from "../../../components/chat/ChatComposer";
import { TokenUsageIndicator } from "../../../components/chat/TokenUsageIndicator";
import { Button } from "../../../components/ui/button";
import { PillSelect } from "../../../components/ui/pill-select";
import type { AgentResponse } from "../../../services/agents/AgentApiService";
import styles from "./ConversationStartComposer.module.css";

export type ConversationStartMode = "chat" | "image";

interface ConversationStartComposerProps {
  agents: AgentResponse[];
  selectedAgentId: string;
  prompt: string;
  mode: ConversationStartMode;
  deepResearchEnabled: boolean;
  debugEnabled: boolean;
  showDeepResearch: boolean;
  creating: boolean;
  error: string | null;
  onAgentChange: (agentId: string) => void;
  onPromptChange: (value: string) => void;
  onModeChange: (mode: ConversationStartMode) => void;
  onDeepResearchChange: (enabled: boolean) => void;
  onDebugChange: (enabled: boolean) => void;
  onSubmit: () => void;
  onCreateAgent: () => void;
}

export function ConversationStartComposer({
  agents,
  selectedAgentId,
  prompt,
  mode,
  deepResearchEnabled,
  debugEnabled,
  showDeepResearch,
  creating,
  error,
  onAgentChange,
  onPromptChange,
  onModeChange,
  onDeepResearchChange,
  onDebugChange,
  onSubmit,
  onCreateAgent,
}: ConversationStartComposerProps) {
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
    <section className={styles.section}>
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

      {error && (
        <div className={styles.errorBanner}>
          {error}
        </div>
      )}

      <ChatComposer
        value={prompt}
        disabled={creating}
        isSubmitting={creating}
        placeholder={mode === "image" ? "Describe the image you want" : "Ask anything"}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        statusIndicator={<TokenUsageIndicator agentId={selectedAgentId || undefined} />}
        imageAction={{
          active: mode === "image",
          disabled: !supportsImage,
          onClick: () => onModeChange(mode === "image" ? "chat" : "image"),
          title: supportsImage
            ? "Create an image"
            : "Selected agent does not support image generation",
        }}
        deepResearchAction={
          showDeepResearch
            ? {
                enabled: deepResearchEnabled,
                disabled: mode === "image",
                onChange: onDeepResearchChange,
              }
            : undefined
        }
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
