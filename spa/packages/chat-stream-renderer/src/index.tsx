import type { ReactNode } from 'react';

export type ChatRole = 'user' | 'assistant';

export type RenderMessage = {
  id: string;
  role: ChatRole;
  content: string;
};

export type RenderToolActivity = {
  id: string;
  toolName: string;
  status: 'running' | 'success' | 'error';
  output?: string;
};

export type ChatRendererFlags = {
  renderDynamicForm?: boolean;
  showToolExecution?: boolean;
  showTypingIndicator?: boolean;
};

export type ChatStreamRendererProps = {
  messages: RenderMessage[];
  streamingContent?: string;
  isLoading?: boolean;
  toolActivities?: RenderToolActivity[];
  flags?: ChatRendererFlags;

  /** Render message content (e.g. markdown). */
  renderContent: (content: string) => ReactNode;

  /** Optional nodes injected inline (forms, status, etc.) */
  formNode?: ReactNode;
  statusNode?: ReactNode;
};

export function ChatStreamRenderer({
  messages,
  streamingContent,
  isLoading,
  toolActivities = [],
  flags = {},
  renderContent,
  formNode,
  statusNode,
}: ChatStreamRendererProps) {
  const showTyping = flags.showTypingIndicator !== false;

  return (
    <>
      {messages.map((msg) => (
        <div key={msg.id} className={`innomight-message innomight-message-${msg.role}`}>
          {renderContent(msg.content)}
        </div>
      ))}

      {flags.showToolExecution && toolActivities.length > 0 && (
        <div className="innomight-message innomight-message-assistant">
          <div className="innomight-tools">
            {toolActivities.map((t) => (
              <div key={t.id} className={`innomight-tool innomight-tool-${t.status}`}>
                <div className="innomight-tool-title">
                  {t.toolName} — {t.status}
                </div>
                {t.output && <div className="innomight-tool-output">{t.output}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {streamingContent && (
        <div className="innomight-message innomight-message-assistant">
          {renderContent(streamingContent)}
        </div>
      )}

      {flags.renderDynamicForm && formNode}
      {statusNode}

      {showTyping && isLoading && !streamingContent && (
        <div className="innomight-typing">
          <div className="innomight-typing-dot" />
          <div className="innomight-typing-dot" />
          <div className="innomight-typing-dot" />
        </div>
      )}
    </>
  );
}
