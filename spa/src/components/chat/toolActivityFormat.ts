import type { ToolActivity } from "../../types/message";

const SENSITIVE_KEY_PATTERN = /token|secret|password|credential|authorization|api[-_]?key/i;
const MAX_ARG_KEYS = 4;
const MAX_VALUE_CHARS = 40;
const MAX_ARGS_LABEL_CHARS = 80;

type ArgsFormatter = (args: Record<string, unknown> | undefined) => string | null;

/**
 * One entry per tool we control the meaning of (native memory/knowledge
 * tools, skill wrappers) — plain-English phrasing of what it's doing.
 * MCP tool calls (`call_mcp_tool` / `list_mcp_tools`) are deliberately absent:
 * we don't own those names, so they fall through to the generic code-style
 * label instead of a guessed-at phrase.
 */
const KNOWN_TOOL_LABELS: Record<string, ArgsFormatter> = {
  execute_skill_action: formatSkillAction,
  load_skill: (args) => {
    const skillName = skillNameFrom(args);
    return skillName ? `Loading ${skillName}` : null;
  },
  check_tool_job: () => "Checking task progress",
  core_memory_read: (args) => withBlock("Reading core memory", args),
  core_memory_append: (args) => withBlock("Appending to core memory", args),
  core_memory_replace: formatCoreMemoryReplace,
  core_memory_delete: formatCoreMemoryDelete,
  core_memory_list_blocks: () => "Listing core memory blocks",
  archival_memory_insert: () => "Storing to archival memory",
  archival_memory_search: (args) => withQuery("Searching archival memory", args),
  recall_conversation: () => "Recalling earlier conversation",
  knowledge_base_search: (args) => withQuery("Searching the knowledge base", args),
  wait: formatWait,
};

export function toolActivityTitle(activity: ToolActivity): string {
  const label = KNOWN_TOOL_LABELS[activity.tool_name]?.(activity.tool_args);
  return label ?? formatGeneric(activity);
}

function formatSkillAction(args: Record<string, unknown> | undefined): string | null {
  const skillName = skillNameFrom(args);
  const action = stringArgument(args, "action");
  if (skillName && action) return `${skillName} · ${humanizeIdentifier(action)}`;
  if (action) return humanizeIdentifier(action);
  return skillName;
}

function formatCoreMemoryReplace(args: Record<string, unknown> | undefined): string {
  const lineNumber = numberArgument(args, "line_number");
  const base = lineNumber != null ? `Replacing line ${lineNumber} in core memory` : "Replacing a line in core memory";
  return withBlock(base, args);
}

function formatCoreMemoryDelete(args: Record<string, unknown> | undefined): string {
  const lineNumber = numberArgument(args, "line_number");
  const base = lineNumber != null ? `Deleting line ${lineNumber} from core memory` : "Deleting a line from core memory";
  return withBlock(base, args);
}

function formatWait(args: Record<string, unknown> | undefined): string {
  const reason = stringArgument(args, "reason");
  return reason ? `Waiting — ${humanizeSentence(reason)}` : "Waiting";
}

function withBlock(base: string, args: Record<string, unknown> | undefined): string {
  const block = stringArgument(args, "block");
  return block ? `${base} (${block})` : base;
}

function withQuery(base: string, args: Record<string, unknown> | undefined): string {
  const query = stringArgument(args, "query");
  return query ? `${base} for "${truncateValue(query)}"` : base;
}

/** Generic fallback for tools we don't have a hand-written phrase for (e.g. MCP calls): renders as a code-style call, e.g. `searchJiraIssuesUsingJql({ cloudId, jql })`. */
function formatGeneric(activity: ToolActivity): string {
  const name = activity.display_tool_name ?? activity.tool_name;
  const args = activity.display_tool_args ?? activity.tool_args;
  return callLabel(name, args);
}

function callLabel(toolName: string, args: Record<string, unknown> | undefined): string {
  const summary = summarizeArgs(args);
  return summary ? `${toolName}({ ${summary} })` : `${toolName}()`;
}

function summarizeArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  const keys = Object.keys(args).slice(0, MAX_ARG_KEYS);
  if (keys.length === 0) return "";

  const withValues = keys
    .map((key) => {
      if (SENSITIVE_KEY_PATTERN.test(key)) return key;
      const formatted = formatArgValue(args[key]);
      return formatted !== null ? `${key}: ${formatted}` : key;
    })
    .join(", ");

  return withValues.length <= MAX_ARGS_LABEL_CHARS ? withValues : keys.join(", ");
}

function formatArgValue(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? `"${truncateValue(trimmed)}"` : null;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return null;
}

function skillNameFrom(args: Record<string, unknown> | undefined): string | null {
  const skillId = stringArgument(args, "skill_id");
  return skillId ? humanizeIdentifier(skillId.split(":", 1)[0]) : null;
}

function stringArgument(args: Record<string, unknown> | undefined, key: string): string | null {
  const value = args?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberArgument(args: Record<string, unknown> | undefined, key: string): number | null {
  const value = args?.[key];
  return typeof value === "number" ? value : null;
}

function truncateValue(value: string): string {
  return value.length > MAX_VALUE_CHARS ? `${value.slice(0, MAX_VALUE_CHARS)}…` : value;
}

function humanizeIdentifier(value: string): string {
  return value
    .split(/[._:\-/]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function humanizeSentence(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
