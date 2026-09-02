import { Bot, Plus } from "lucide-react";
import { ChatComposer } from "../../../components/chat/ChatComposer";
import { Button } from "../../../components/ui/button";
import { PillSelect } from "../../../components/ui/pill-select";
import type { AgentResponse } from "../../../services/agents/AgentApiService";

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
      <section className="flex w-full max-w-3xl flex-col gap-5">
        <div>
          <h1 className="text-2xl font-semibold leading-8 text-[var(--text-primary)]">Start a conversation</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-[var(--text-muted)]">
            Create an agent before starting a conversation.
          </p>
        </div>
        <Button className="self-start" onClick={onCreateAgent}>
          <Plus className="h-4 w-4" />
          Create Agent
        </Button>
      </section>
    );
  }

  return (
    <section className="flex w-full max-w-5xl flex-col gap-8">
      <div>
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-white/5 text-[var(--text-secondary)]">
          <Bot className="h-5 w-5" />
        </div>
        <h1 className="text-3xl font-semibold leading-9 text-[var(--text-primary)]">
          Start a conversation
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--text-muted)]">
          Ask your first question, create an image, or continue an older chat from the conversation list.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {selectedAgent?.agent_description && (
        <p className="-mt-4 max-w-3xl text-xs leading-5 text-[var(--text-muted)]">
          {selectedAgent.agent_description}
        </p>
      )}

      <ChatComposer
        value={prompt}
        disabled={creating}
        isSubmitting={creating}
        placeholder={mode === "image" ? "Describe the image you want" : "Ask anything"}
        onChange={onPromptChange}
        onSubmit={onSubmit}
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
