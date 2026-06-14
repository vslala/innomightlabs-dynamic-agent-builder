import { Bot, Image as ImageIcon, Plus } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { ExpandableChatBox } from "../../../components/ui/expandable-chat-box";
import { PillSelect } from "../../../components/ui/pill-select";
import type { AgentResponse } from "../../../services/agents/AgentApiService";

export type ConversationStartMode = "chat" | "image";

interface ConversationStartComposerProps {
  agents: AgentResponse[];
  selectedAgentId: string;
  prompt: string;
  mode: ConversationStartMode;
  creating: boolean;
  error: string | null;
  onAgentChange: (agentId: string) => void;
  onPromptChange: (value: string) => void;
  onModeChange: (mode: ConversationStartMode) => void;
  onSubmit: () => void;
  onCreateAgent: () => void;
}

export function ConversationStartComposer({
  agents,
  selectedAgentId,
  prompt,
  mode,
  creating,
  error,
  onAgentChange,
  onPromptChange,
  onModeChange,
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

      <ExpandableChatBox
        value={prompt}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        isSubmitting={creating}
        placeholder={mode === "image" ? "Describe the image you want" : "Ask anything"}
        leftActions={
          <Button
            type="button"
            variant={mode === "image" ? "default" : "ghost"}
            size="icon"
            disabled={!supportsImage}
            onClick={() => onModeChange(mode === "image" ? "chat" : "image")}
            title={supportsImage ? "Create an image" : "Selected agent does not support image generation"}
            className="h-10 w-10 rounded-full"
          >
            <ImageIcon className="h-4 w-4" />
          </Button>
        }
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
