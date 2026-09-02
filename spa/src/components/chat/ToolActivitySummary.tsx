import { CheckCircle2, Loader2, Wrench, XCircle } from "lucide-react";

import type { ToolActivity } from "../../types/message";
import { AccordionPanel, Card } from "../ui";
import styles from "./ToolActivitySummary.module.css";

interface ToolActivitySummaryProps {
  activities: ToolActivity[];
}

export function ToolActivitySummary({ activities }: ToolActivitySummaryProps) {
  const isRunning = activities.some((activity) => activity.status === "running");

  return (
    <AccordionPanel
      defaultOpen
      title={
        <span className={styles.heading}>
          <Wrench aria-hidden="true" />
          Agent activity
        </span>
      }
      trailing={
        <span className={styles.count}>
          {isRunning ? "Working" : "Finished"} · {activities.length} {activities.length === 1 ? "step" : "steps"}
        </span>
      }
      style={{
        margin: "0.5rem 0",
        borderColor: "var(--border-default)",
        borderRadius: "var(--radius-lg)",
        backgroundColor: "var(--surface-subtle)",
      }}
      bodyStyle={{ padding: "0 var(--space-3) var(--space-3)" }}
    >
      <div className={styles.list}>
        {activities.map((activity) => (
          <ToolActivitySummaryItem key={activity.id} activity={activity} />
        ))}
      </div>
    </AccordionPanel>
  );
}

function ToolActivitySummaryItem({ activity }: { activity: ToolActivity }) {
  const StatusIcon = activity.status === "running" ? Loader2 : activity.status === "success" ? CheckCircle2 : XCircle;

  return (
    <Card className={styles.item} data-status={activity.status}>
      <StatusIcon
        className={activity.status === "running" ? styles.spinner : styles.statusIcon}
        aria-hidden="true"
      />
      <span className={styles.title}>{toolActivityTitle(activity)}</span>
      <span className={styles.status}>
        {activity.status === "running" ? "In progress" : activity.status === "success" ? "Done" : "Failed"}
      </span>
    </Card>
  );
}

function toolActivityTitle(activity: ToolActivity): string {
  const skillId = stringArgument(activity.tool_args, "skill_id");
  const action = stringArgument(activity.tool_args, "action");
  const skillName = skillId ? humanizeIdentifier(skillId.split(":", 1)[0]) : null;

  if (activity.tool_name === "execute_skill_action") {
    if (skillName && action) return `${skillName} · ${humanizeIdentifier(action)}`;
    if (action) return humanizeIdentifier(action);
    if (skillName) return skillName;
  }

  if (activity.tool_name === "load_skill" && skillName) {
    return `Loading ${skillName}`;
  }

  if (activity.tool_name === "check_tool_job") {
    return "Checking task progress";
  }

  return humanizeIdentifier(activity.tool_name);
}

function stringArgument(args: Record<string, unknown> | undefined, key: string): string | null {
  const value = args?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function humanizeIdentifier(value: string): string {
  return value
    .split(/[._:\-/]+/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
