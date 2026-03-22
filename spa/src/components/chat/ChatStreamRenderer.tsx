import { ChatStreamRenderer as BaseRenderer } from '../../../packages/chat-stream-renderer/src';
import type {
  ChatRendererFlags,
  RenderMessage,
  RenderToolActivity,
} from '../../../packages/chat-stream-renderer/src';
import { MarkdownRenderer } from '../ui/markdown-renderer';

export type { ChatRendererFlags, RenderMessage, RenderToolActivity };

export function ChatStreamRenderer(props: {
  messages: RenderMessage[];
  streamingContent?: string;
  isLoading?: boolean;
  toolActivities?: RenderToolActivity[];
  flags?: ChatRendererFlags;
  formNode?: React.ReactNode;
  statusNode?: React.ReactNode;
}) {
  const { messages, streamingContent, isLoading, toolActivities, flags, formNode, statusNode } = props;

  return (
    <BaseRenderer
      messages={messages}
      streamingContent={streamingContent}
      isLoading={isLoading}
      toolActivities={toolActivities}
      flags={flags}
      formNode={formNode}
      statusNode={statusNode}
      renderContent={(content) => <MarkdownRenderer content={content} />}
    />
  );
}
