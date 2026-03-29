/** @jsxImportSource preact */
import type { ComponentChildren } from 'preact';
import { buildChatStreamRenderPlan } from '../../../packages/chat-stream-renderer/src';
import type { Message } from '../types';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ChatStreamRendererProps {
  messages: Message[];
  streamingContent?: string;
  isLoading?: boolean;
  extraNode?: ComponentChildren;
}

export function ChatStreamRenderer({
  messages,
  streamingContent,
  isLoading,
  extraNode,
}: ChatStreamRendererProps) {
  const plan = buildChatStreamRenderPlan({
    messages,
    getMessageKey: (message) => message.id,
    streamingContent,
    hasExtraNode: Boolean(extraNode),
    isLoading,
  });

  return (
    <>
      {plan.map((item) => {
        if (item.kind === 'message') {
          return (
            <div key={item.key} className={`innomight-message innomight-message-${item.message.role}`}>
              <MarkdownRenderer content={item.message.content} />
            </div>
          );
        }

        if (item.kind === 'streaming') {
          return (
            <div key={item.key} className="innomight-message innomight-message-assistant">
              <MarkdownRenderer content={item.content} />
            </div>
          );
        }

        if (item.kind === 'extra') {
          return <div key={item.key}>{extraNode}</div>;
        }

        return (
          <div key={item.key} className="innomight-typing">
            <div className="innomight-typing-dot" />
            <div className="innomight-typing-dot" />
            <div className="innomight-typing-dot" />
          </div>
        );
      })}
    </>
  );
}
