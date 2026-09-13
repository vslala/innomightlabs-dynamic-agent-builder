/**
 * Run status helpers shared by the cards, the drawer, and the top bar.
 */

import type { StatusBadgeProps } from "../../../../components/ui";
import type {
  AutomationNodeRunStatus,
  AutomationRunStatus,
} from "../../../../types/automation";

export function runBadgeStatus(
  status: AutomationRunStatus | AutomationNodeRunStatus
): StatusBadgeProps["status"] {
  if (status === "succeeded") return "success";
  if (status === "running") return "in_progress";
  if (status === "skipped") return "inactive";
  return status;
}

export function formatRunTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatRelativeTime(value: string): string {
  const elapsed = Date.now() - new Date(value).getTime();
  const minutes = Math.round(elapsed / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatRunTime(value);
}

export function formatDuration(startedAt: string, completedAt?: string | null): string | null {
  if (!completedAt) return null;
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.round((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
}
