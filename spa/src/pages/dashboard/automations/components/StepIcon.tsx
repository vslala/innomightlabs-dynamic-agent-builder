import { Bot, CalendarClock, GitBranch, Globe, Mail, Zap } from "lucide-react";

import type { StepIconKind } from "../chain/actionSummary";

const ICONS: Record<StepIconKind, typeof Bot> = {
  agent: Bot,
  email: Mail,
  calendar: CalendarClock,
  web: Globe,
  condition: GitBranch,
  action: Zap,
};

export function StepIcon({ kind }: { kind: StepIconKind }) {
  const Icon = ICONS[kind] ?? Zap;
  return <Icon className="h-4 w-4" />;
}
