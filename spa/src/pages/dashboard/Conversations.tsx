import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, Send, MessageSquare } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { ScrollArea } from "../../components/ui/scroll-area";
import { Avatar, AvatarFallback } from "../../components/ui/avatar";
import { cn } from "../../lib/utils";
import { getAgentService } from "../../services/agents";
import type { Conversation, ChatMessage, Agent } from "../../types/agent";

export function Conversations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(
    searchParams.get("agent")
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadData = async () => {
    const service = getAgentService();
    const [conversationsData, agentsData] = await Promise.all([
      service.getConversations(),
      service.getAgents(),
    ]);
    setConversations(conversationsData);
    setAgents(agentsData);
    setLoading(false);
  };

  const loadMessages = async (agentId: string) => {
    const service = getAgentService();
    const messagesData = await service.getMessages(agentId);
    setMessages(messagesData);
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (selectedAgentId) {
      loadMessages(selectedAgentId);
      setSearchParams({ agent: selectedAgentId });
    }
  }, [selectedAgentId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSendMessage = async () => {
    if (!newMessage.trim() || !selectedAgentId || sending) return;

    setSending(true);
    const service = getAgentService();
    await service.sendMessage(selectedAgentId, newMessage);
    setNewMessage("");
    await loadMessages(selectedAgentId);
    await loadData(); // Refresh conversations list
    setSending(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const selectedAgent = agents.find((a) => a.id === selectedAgentId);

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const formatDate = (timestamp: string) => {
    const date = new Date(timestamp);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return "Today";
    } else if (date.toDateString() === yesterday.toDateString()) {
      return "Yesterday";
    }
    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--gradient-start)] border-t-transparent" />
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <div className="flex items-center justify-center h-[calc(100vh-12rem)]">
        <div className="text-center">
          <MessageSquare className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
          <h3 className="text-lg font-medium text-[var(--text-primary)] mb-2">
            No agents to chat with
          </h3>
          <p className="text-[var(--text-muted)] mb-4">
            Create an agent first to start a conversation
          </p>
          <Button asChild>
            <a href="/dashboard/agents">Create an Agent</a>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-10rem)] rounded-lg border border-[var(--border-subtle)] overflow-hidden bg-white/[0.01]">
      {/* Conversations Sidebar */}
      <div className="w-72 border-r border-[var(--border-subtle)] flex flex-col bg-white/[0.01]">
        <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Conversations</h2>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2">
            {agents.map((agent) => {
              const conversation = conversations.find(
                (c) => c.agentId === agent.id
              );
              const isSelected = selectedAgentId === agent.id;

              return (
                <button
                  key={agent.id}
                  onClick={() => setSelectedAgentId(agent.id)}
                  className={cn(
                    "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors",
                    isSelected
                      ? "bg-gradient-to-r from-[var(--gradient-start)]/20 to-[var(--gradient-mid)]/20 border border-[var(--gradient-start)]/30"
                      : "hover:bg-white/5"
                  )}
                >
                  <Avatar className="h-10 w-10">
                    <AvatarFallback className="bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
                      <Bot className="h-5 w-5 text-white" />
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-[var(--text-primary)] truncate">
                        {agent.name}
                      </p>
                      {conversation?.lastMessageAt && (
                        <span className="text-xs text-[var(--text-muted)]">
                          {formatTime(conversation.lastMessageAt)}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-[var(--text-muted)] truncate">
                      {conversation?.lastMessage || "No messages yet"}
                    </p>
                  </div>
                  {conversation && conversation.messageCount > 0 && (
                    <span className="h-5 min-w-[1.25rem] px-1 rounded-full bg-[var(--gradient-start)] text-white text-xs font-medium flex items-center justify-center">
                      {conversation.messageCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </ScrollArea>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        {selectedAgentId ? (
          <>
            {/* Chat Header */}
            <div className="p-4 border-b border-[var(--border-subtle)] flex items-center gap-3">
              <Avatar className="h-10 w-10">
                <AvatarFallback className="bg-gradient-to-br from-[var(--gradient-start)] to-[var(--gradient-mid)]">
                  <Bot className="h-5 w-5 text-white" />
                </AvatarFallback>
              </Avatar>
              <div>
                <p className="font-medium text-[var(--text-primary)]">
                  {selectedAgent?.name}
                </p>
                <p className="text-sm text-[var(--text-muted)]">
                  {selectedAgent?.agentModel}
                </p>
              </div>
            </div>

            {/* Messages */}
            <ScrollArea className="flex-1 p-4">
              <div className="space-y-4">
                {messages.length === 0 ? (
                  <div className="text-center py-12">
                    <MessageSquare className="h-12 w-12 mx-auto text-[var(--text-muted)] mb-3" />
                    <p className="text-[var(--text-muted)]">No messages yet</p>
                    <p className="text-sm text-[var(--text-muted)] mt-1">
                      Start the conversation by sending a message
                    </p>
                  </div>
                ) : (
                  messages.map((message, index) => {
                    const showDate =
                      index === 0 ||
                      formatDate(message.timestamp) !==
                        formatDate(messages[index - 1].timestamp);

                    return (
                      <div key={message.id}>
                        {showDate && (
                          <div className="flex justify-center my-4">
                            <span className="px-3 py-1 rounded-full bg-white/5 text-xs text-[var(--text-muted)]">
                              {formatDate(message.timestamp)}
                            </span>
                          </div>
                        )}
                        <div
                          className={cn(
                            "flex",
                            message.role === "user"
                              ? "justify-end"
                              : "justify-start"
                          )}
                        >
                          <div
                            className={cn(
                              "max-w-[70%] rounded-2xl px-4 py-2",
                              message.role === "user"
                                ? "bg-gradient-to-r from-[var(--gradient-start)] to-[var(--gradient-mid)] text-white"
                                : "bg-white/5 text-[var(--text-primary)]"
                            )}
                          >
                            <p className="text-sm whitespace-pre-wrap">
                              {message.content}
                            </p>
                            <p
                              className={cn(
                                "text-xs mt-1",
                                message.role === "user"
                                  ? "text-white/70"
                                  : "text-[var(--text-muted)]"
                              )}
                            >
                              {formatTime(message.timestamp)}
                            </p>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            {/* Message Input */}
            <div className="p-4 border-t border-[var(--border-subtle)]">
              <div className="flex gap-2">
                <Input
                  placeholder="Type a message..."
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  disabled={sending}
                  className="flex-1"
                />
                <Button
                  onClick={handleSendMessage}
                  disabled={!newMessage.trim() || sending}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <MessageSquare className="h-16 w-16 mx-auto text-[var(--text-muted)] mb-4" />
              <p className="text-[var(--text-muted)]">
                Select a conversation to start chatting
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
