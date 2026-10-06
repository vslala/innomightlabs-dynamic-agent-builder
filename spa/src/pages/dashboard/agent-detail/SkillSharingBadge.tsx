import { Lock, Users } from "lucide-react";

import { Pill } from "../../../components/ui";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../../../components/ui/tooltip";

const ONLY_YOU =
  "Uses your own accounts or machine, so it can't be shared with widget visitors, API keys or A2A agents.";
const SHAREABLE = "After installing, you choose who besides you can use it.";

/** Whether a skill can ever be shared, shown before it is installed as well as after. */
export function SkillSharingBadge({ ownerOnly }: { ownerOnly: boolean }) {
  const Icon = ownerOnly ? Lock : Users;
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Pill variant={ownerOnly ? "outline" : "info"} size="sm" className="agent-skill-sharing" tabIndex={0}>
            <Icon aria-hidden="true" />
            {ownerOnly ? "Only you" : "Shareable"}
          </Pill>
        </TooltipTrigger>
        <TooltipContent>{ownerOnly ? ONLY_YOU : SHAREABLE}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
