import { StatusBadge } from "../../../../components/ui";
import type {
  AutomationNodeRunStatus,
  AutomationRunStatus,
} from "../../../../types/automation";
import { runBadgeStatus } from "./runStatus";

export function RunStatusBadge({
  status,
  label,
}: {
  status: AutomationRunStatus | AutomationNodeRunStatus;
  label?: string;
}) {
  return <StatusBadge status={runBadgeStatus(status)} label={label ?? status} />;
}
