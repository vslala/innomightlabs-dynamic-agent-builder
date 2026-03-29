export type ChatStreamRenderItem<TMessage> =
  | {
      kind: 'message';
      key: string;
      message: TMessage;
      index: number;
    }
  | {
      kind: 'streaming';
      key: 'streaming';
      content: string;
    }
  | {
      kind: 'extra';
      key: 'extra';
    }
  | {
      kind: 'typing';
      key: 'typing';
    };

export type BuildChatStreamRenderPlanProps<TMessage> = {
  messages: TMessage[];
  getMessageKey: (message: TMessage, index: number) => string;
  streamingContent?: string;
  hasExtraNode?: boolean;
  isLoading?: boolean;
  showTypingIndicator?: boolean;
};

export function buildChatStreamRenderPlan<TMessage>({
  messages,
  getMessageKey,
  streamingContent,
  hasExtraNode,
  isLoading,
  showTypingIndicator = true,
}: BuildChatStreamRenderPlanProps<TMessage>): ChatStreamRenderItem<TMessage>[] {
  const items: ChatStreamRenderItem<TMessage>[] = messages.map((message, index) => ({
    kind: 'message',
    key: getMessageKey(message, index),
    message,
    index,
  }));

  if (streamingContent) {
    items.push({
      kind: 'streaming',
      key: 'streaming',
      content: streamingContent,
    });
  }

  if (hasExtraNode) {
    items.push({
      kind: 'extra',
      key: 'extra',
    });
  }

  if (isLoading && !streamingContent && showTypingIndicator) {
    items.push({
      kind: 'typing',
      key: 'typing',
    });
  }

  return items;
}
