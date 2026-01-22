/** @jsxImportSource preact */
import { useState, useRef, useEffect } from 'preact/hooks';
import { Message, Conversation } from '../types';
import { sendMessage } from '../api';
import { SendIcon } from './Icons';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ChatWindowProps {
  conversation: Conversation;
  messages: Message[];
  onMessagesChange: (messages: Message[]) => void;
  onClose: () => void;
  placeholder?: string;
}

export function ChatWindow({
  conversation,
  messages,
  onMessagesChange,
  onClose,
  placeholder = 'Type a message...',
}: ChatWindowProps) {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSend = async () => {
    const content = input.trim();
    if (!content || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date(),
    };
    onMessagesChange([...messages, userMessage]);
    setInput('');
    setIsLoading(true);
    setStreamingContent('');

    try {
      let assistantContent = '';

      for await (const event of sendMessage(conversation.conversationId, content)) {
        if (event.event_type === 'AGENT_RESPONSE_TO_USER') {
          assistantContent += event.content;
          setStreamingContent(assistantContent);
        } else if (event.event_type === 'ERROR') {
          throw new Error(event.content);
        }
      }

      // Add assistant message
      if (assistantContent) {
        const assistantMessage: Message = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: assistantContent,
          timestamp: new Date(),
        };
        onMessagesChange([...messages, userMessage, assistantMessage]);
      }
    } catch (error) {
      // Add error message
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: error instanceof Error ? error.message : 'An error occurred',
        timestamp: new Date(),
      };
      onMessagesChange([...messages, userMessage, errorMessage]);
    } finally {
      setIsLoading(false);
      setStreamingContent('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Messages */}
      <div className="innomight-messages">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`innomight-message innomight-message-${msg.role}`}
          >
            <MarkdownRenderer content={msg.content} />
          </div>
        ))}

        {/* Streaming response */}
        {streamingContent && (
          <div className="innomight-message innomight-message-assistant">
            <MarkdownRenderer content={streamingContent} />
          </div>
        )}

        {/* Typing indicator */}
        {isLoading && !streamingContent && (
          <div className="innomight-typing">
            <div className="innomight-typing-dot" />
            <div className="innomight-typing-dot" />
            <div className="innomight-typing-dot" />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="innomight-input-area">
        <input
          type="text"
          className="innomight-input"
          value={input}
          onInput={(e) => setInput((e.target as HTMLInputElement).value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={isLoading}
        />
        <button
          className="innomight-send-btn"
          onClick={handleSend}
          disabled={!input.trim() || isLoading}
          aria-label="Send message"
        >
          <SendIcon />
        </button>
      </div>
    </>
  );
}
