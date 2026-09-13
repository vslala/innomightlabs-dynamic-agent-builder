import { CircleCheck } from "lucide-react";

import type { AutomationNode } from "../../../../types/automation";

export function EndCard({ node }: { node: AutomationNode }) {
  return (
    <div className="chain-card chain-card--end">
      <span className="chain-card__gutter">END</span>
      <CircleCheck className="h-4 w-4 chain-card__icon" />
      <span className="chain-card__title">{node.name || "Done"}</span>
      <span className="chain-card__subtitle">Nothing runs after this</span>
    </div>
  );
}
