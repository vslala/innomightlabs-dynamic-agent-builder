import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  Check,
  Clipboard,
  Clock,
  Loader2,
  Network,
  RefreshCw,
} from "lucide-react";

import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { AccordionPanel } from "../../../components/ui/accordion-panel";
import { JsonTreeViewer } from "../../../components/ui/json-viewer";
import { SearchInput } from "../../../components/ui/search-input";
import { StatusBadge } from "../../../components/ui/status-badge";
import { cn } from "../../../lib/utils";
import {
  agentApiService,
  type Agent2AgentMessage,
  type Agent2AgentTask,
  type Agent2AgentTaskState,
} from "../../../services/agents/AgentApiService";
import { useAgentDetailContext } from "./types";
import "./AgentA2ATasksPage.css";

type BadgeStatus = "pending" | "in_progress" | "completed" | "failed" | "cancelled";
type TaskContextGroup = {
  contextId: string;
  conversationId: string;
  clientKeyId: string;
  tasks: Agent2AgentTask[];
  failedCount: number;
  latestUpdatedAt: string;
};

export function AgentA2ATasksPage() {
  const { agent } = useAgentDetailContext();
  const [tasks, setTasks] = useState<Agent2AgentTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedValue, setCopiedValue] = useState<string | null>(null);

  const loadTasks = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);
    try {
      const response = await agentApiService.listAgent2AgentTasks(agent.agent_id);
      setTasks(response.items);
      setSelectedTaskId((current) => current ?? response.items[0]?.id ?? null);
    } catch (err) {
      console.error("Error loading A2A tasks:", err);
      setError("Failed to load Agent2Agent tasks.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [agent.agent_id]);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  const filteredTasks = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return tasks;
    return tasks.filter((task) => {
      const requestText = firstMessageText(task.history[0]).toLowerCase();
      const responseText = messageText(task.status.message).toLowerCase();
      return (
        task.id.toLowerCase().includes(query) ||
        task.contextId.toLowerCase().includes(query) ||
        task.conversationId.toLowerCase().includes(query) ||
        task.clientKeyId.toLowerCase().includes(query) ||
        statusLabel(task.status.state).toLowerCase().includes(query) ||
        requestText.includes(query) ||
        responseText.includes(query)
      );
    });
  }, [search, tasks]);

  const contextGroups = useMemo(() => groupTasksByContext(filteredTasks), [filteredTasks]);

  const selectedTask =
    filteredTasks.find((task) => task.id === selectedTaskId) ??
    filteredTasks[0] ??
    null;

  const copyValue = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedValue(label);
      window.setTimeout(() => setCopiedValue(null), 1800);
    } catch (err) {
      console.error("Failed to copy A2A task value:", err);
    }
  };

  if (loading) {
    return (
      <div className="a2a-tasks-loading">
        <Loader2 className="a2a-tasks-loading__icon" />
      </div>
    );
  }

  return (
    <div className="a2a-tasks-page">
      <Card>
        <CardHeader>
          <div className="a2a-tasks-header">
            <div className="a2a-tasks-title-group">
              <span className="a2a-tasks-title-icon">
                <Network className="a2a-tasks-icon" />
              </span>
              <div>
                <CardTitle className="a2a-tasks-card-title">Agent2Agent Tasks</CardTitle>
                <p className="a2a-tasks-description">
                  External A2A calls for this agent, grouped by conversation context.
                </p>
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void loadTasks({ silent: true })}
              disabled={refreshing}
            >
              {refreshing ? (
                <Loader2 className="a2a-tasks-button-icon a2a-tasks-spin" />
              ) : (
                <RefreshCw className="a2a-tasks-button-icon" />
              )}
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="a2a-tasks-content">
          {error ? (
            <div className="a2a-tasks-page-error">
              <AlertCircle className="a2a-tasks-button-icon" />
              {error}
            </div>
          ) : null}

          <div className="a2a-tasks-layout">
            <div className="a2a-tasks-list-panel">
              <div className="a2a-tasks-list-header">
                <div className="a2a-tasks-list-title-row">
                  <div>
                    <h2 className="a2a-tasks-section-title">Contexts</h2>
                    <p className="a2a-tasks-section-caption">
                      {contextGroups.length} contexts, {tasks.length} tasks
                    </p>
                  </div>
                </div>
                <div className="a2a-tasks-search">
                  <SearchInput
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search contexts and tasks"
                    aria-label="Search A2A contexts and tasks"
                  />
                </div>
              </div>

              <div className="a2a-tasks-list-body">
                {filteredTasks.length === 0 ? (
                  <div className="a2a-tasks-empty">
                    <Network className="a2a-tasks-empty-icon" />
                    No A2A contexts found.
                  </div>
                ) : (
                  <ContextTaskList
                    groups={contextGroups}
                    selectedTaskId={selectedTask?.id ?? null}
                    onSelectTask={setSelectedTaskId}
                  />
                )}
              </div>
            </div>

            <div className="a2a-task-detail-panel">
              {selectedTask ? (
                <TaskDetail
                  task={selectedTask}
                  copiedValue={copiedValue}
                  onCopy={copyValue}
                />
              ) : (
                <div className="a2a-task-detail-empty">
                  Select a task to inspect it.
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function ContextTaskList({
  groups,
  selectedTaskId,
  onSelectTask,
}: {
  groups: TaskContextGroup[];
  selectedTaskId: string | null;
  onSelectTask: (taskId: string) => void;
}) {
  return (
    <div className="a2a-context-list">
      {groups.map((group) => {
        const selectedInGroup = group.tasks.some((task) => task.id === selectedTaskId);
        const latestTask = group.tasks[0];

        return (
          <section
            key={group.contextId}
            className={cn(
              "a2a-context-group",
              selectedInGroup && "a2a-context-group--selected",
              group.failedCount > 0 && "a2a-context-group--has-failures"
            )}
          >
            <div className="a2a-context-group__header">
              <div className="a2a-context-group__main">
                <div className="a2a-context-group__title-row">
                  <h3 className="a2a-context-group__title">
                    {contextTitle(group)}
                  </h3>
                  {group.failedCount > 0 ? (
                    <span className="a2a-context-group__failure">
                      {group.failedCount} failed
                    </span>
                  ) : null}
                </div>
                <div className="a2a-context-group__meta">
                  <span>{group.tasks.length} task{group.tasks.length === 1 ? "" : "s"}</span>
                  <span>Updated {formatDateTime(group.latestUpdatedAt)}</span>
                </div>
              </div>
              <code className="a2a-context-group__id">{shortId(group.contextId)}</code>
            </div>

            <div className="a2a-context-group__tasks">
              {group.tasks.map((task, index) => (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => onSelectTask(task.id)}
                  className={cn(
                    "a2a-task-row",
                    selectedTaskId === task.id
                      ? "a2a-task-row--selected"
                      : isFailureState(task.status.state)
                        ? "a2a-task-row--failed"
                        : "a2a-task-row--idle"
                  )}
                  aria-current={selectedTaskId === task.id ? "true" : undefined}
                >
                  <div className="a2a-task-row__main">
                    <span className="a2a-task-row__title">
                      {firstMessageText(task.history[0]) || `Task ${index + 1}`}
                    </span>
                    <TaskStatusBadge state={task.status.state} />
                  </div>
                  <div className="a2a-task-row__meta">
                    <span className="a2a-task-row__time">
                      <Clock className="a2a-task-row__time-icon" />
                      {formatDateTime(task.createdAt)}
                    </span>
                    <code>{shortId(task.id)}</code>
                  </div>
                </button>
              ))}
            </div>

            <div className="a2a-context-group__footer">
              <span>Conversation {shortId(group.conversationId)}</span>
              <span>Key {shortId(group.clientKeyId)}</span>
              {latestTask ? <span>Latest {statusLabel(latestTask.status.state)}</span> : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function TaskDetail({
  task,
  copiedValue,
  onCopy,
}: {
  task: Agent2AgentTask;
  copiedValue: string | null;
  onCopy: (label: string, value: string) => void;
}) {
  const requestText = firstMessageText(task.history[0]);
  const responseText = messageText(task.status.message);
  const isFailure = isFailureState(task.status.state);

  return (
    <article className="a2a-task-detail">
      <section
        className={cn(
          "a2a-task-status",
          isFailure ? "a2a-task-status--failed" : "a2a-task-status--default"
        )}
        aria-live={isFailure ? "polite" : undefined}
      >
        <div className="a2a-task-status__layout">
          <div className="a2a-task-status__main">
            <div className="a2a-task-status__meta">
              <TaskStatusBadge state={task.status.state} />
              <span className="a2a-task-status__updated">
                Updated {formatDateTime(task.updatedAt)}
              </span>
            </div>
            <h2 className="a2a-task-status__title">
              {requestText || "A2A task"}
            </h2>
            {isFailure && responseText ? (
              <p className="a2a-task-status__error">
                {responseText}
              </p>
            ) : null}
          </div>
          <div className="a2a-task-status__created">
            <div>Created</div>
            <div className="a2a-task-status__created-value">{formatDateTime(task.createdAt)}</div>
          </div>
        </div>
      </section>

      <section className="a2a-task-ids" aria-label="Task identifiers">
        <CopyableId label="Task" value={task.id} copied={copiedValue === "task"} onCopy={() => onCopy("task", task.id)} />
        <CopyableId label="Context" value={task.contextId} copied={copiedValue === "context"} onCopy={() => onCopy("context", task.contextId)} />
        <CopyableId label="Conversation" value={task.conversationId} copied={copiedValue === "conversation"} onCopy={() => onCopy("conversation", task.conversationId)} />
        <CopyableId label="Client key" value={task.clientKeyId} copied={copiedValue === "key"} onCopy={() => onCopy("key", task.clientKeyId)} />
      </section>

      <section className="a2a-task-messages">
        <MessagePanel
          title="Request"
          subtitle={task.history[0]?.messageId ? `Message ${shortId(task.history[0].messageId)}` : undefined}
          message={requestText}
          fallback="No request text recorded."
        />
        <MessagePanel
          title={isFailure ? "Error" : "Response"}
          subtitle={task.status.message?.messageId ? `Message ${shortId(task.status.message.messageId)}` : undefined}
          message={responseText}
          fallback="No response message recorded yet."
          tone={isFailure ? "danger" : "default"}
        />
      </section>

      <section className="a2a-task-raw-json">
        <AccordionPanel
          title={<span className="a2a-tasks-section-title">Raw JSON</span>}
          subtitle="Full persisted A2A task payload"
          defaultOpen={false}
          trailing={
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                onCopy("raw", JSON.stringify(task, null, 2));
              }}
            >
              {copiedValue === "raw" ? "Copied" : "Copy"}
            </Button>
          }
        >
          <JsonTreeViewer value={task} maxHeight="24rem" />
        </AccordionPanel>
      </section>
    </article>
  );
}

function CopyableId({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <button
      type="button"
      className="a2a-copy-id"
      onClick={onCopy}
      aria-label={`Copy ${label} ID ${value}`}
      title={value}
    >
      <span className="a2a-copy-id__label">{label}</span>
      <code className="a2a-copy-id__value">{shortId(value)}</code>
      {copied ? <Check className="a2a-copy-id__icon a2a-copy-id__icon--copied" /> : <Clipboard className="a2a-copy-id__icon" />}
    </button>
  );
}

function MessagePanel({
  title,
  subtitle,
  message,
  fallback,
  tone = "default",
}: {
  title: string;
  subtitle?: string;
  message: string;
  fallback: string;
  tone?: "default" | "danger";
}) {
  return (
    <section
      className={cn(
        "a2a-message-panel",
        tone === "danger" && "a2a-message-panel--danger"
      )}
    >
      <div className="a2a-message-panel__header">
        <h3 className="a2a-message-panel__title">{title}</h3>
        {subtitle ? <span className="a2a-message-panel__subtitle">{subtitle}</span> : null}
      </div>
      <div
        className={cn(
          "a2a-message-panel__body",
          tone === "danger" ? "a2a-message-panel__body--danger" : "a2a-message-panel__body--default"
        )}
      >
        {message || <span className="a2a-message-panel__fallback">{fallback}</span>}
      </div>
    </section>
  );
}
function TaskStatusBadge({ state }: { state: Agent2AgentTaskState }) {
  const status = badgeStatus(state);
  return <StatusBadge status={status} label={statusLabel(state)} showIcon />;
}

function badgeStatus(state: Agent2AgentTaskState): BadgeStatus {
  switch (state) {
    case "TASK_STATE_SUBMITTED":
      return "pending";
    case "TASK_STATE_WORKING":
    case "TASK_STATE_INPUT_REQUIRED":
      return "in_progress";
    case "TASK_STATE_COMPLETED":
      return "completed";
    case "TASK_STATE_FAILED":
    case "TASK_STATE_REJECTED":
      return "failed";
    case "TASK_STATE_CANCELED":
      return "cancelled";
  }
}

function groupTasksByContext(tasks: Agent2AgentTask[]): TaskContextGroup[] {
  const groups = new Map<string, Agent2AgentTask[]>();

  for (const task of tasks) {
    const existing = groups.get(task.contextId) ?? [];
    existing.push(task);
    groups.set(task.contextId, existing);
  }

  return Array.from(groups.entries())
    .map(([contextId, contextTasks]) => {
      const sortedTasks = [...contextTasks].sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
      );
      const latestUpdatedAt = sortedTasks.reduce((latest, task) => {
        return new Date(task.updatedAt).getTime() > new Date(latest).getTime()
          ? task.updatedAt
          : latest;
      }, sortedTasks[0].updatedAt);

      return {
        contextId,
        conversationId: sortedTasks[0].conversationId,
        clientKeyId: sortedTasks[0].clientKeyId,
        tasks: sortedTasks,
        failedCount: sortedTasks.filter((task) => isFailureState(task.status.state)).length,
        latestUpdatedAt,
      };
    })
    .sort((a, b) => new Date(b.latestUpdatedAt).getTime() - new Date(a.latestUpdatedAt).getTime());
}

function contextTitle(group: TaskContextGroup): string {
  const firstTaskWithText = [...group.tasks]
    .reverse()
    .find((task) => firstMessageText(task.history[0]));

  return firstTaskWithText
    ? firstMessageText(firstTaskWithText.history[0])
    : `Context ${shortId(group.contextId)}`;
}

function isFailureState(state: Agent2AgentTaskState): boolean {
  return state === "TASK_STATE_FAILED" || state === "TASK_STATE_REJECTED";
}

function statusLabel(state: Agent2AgentTaskState): string {
  return state
    .replace("TASK_STATE_", "")
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function firstMessageText(message?: Agent2AgentMessage): string {
  return messageText(message);
}

function messageText(message?: Agent2AgentMessage | null): string {
  if (!message) return "";
  return message.parts.map((part) => part.text).join("\n").trim();
}

function shortId(value: string): string {
  if (value.length <= 16) return value;
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
