/**
 * Renders a chain as a vertical column of cards, recursing into branch lanes.
 */

import type { ChainItem } from "../chain/chainModel";
import { useChain } from "./chainContext";
import { ConditionCard } from "./ConditionCard";
import { EndCard } from "./EndCard";
import { InsertAffordance } from "./InsertAffordance";
import { StepCard } from "./StepCard";
import { TriggerCard } from "./TriggerCard";

export function ChainColumn({ items }: { items: ChainItem[] }) {
  const { readOnly, onOpenPalette } = useChain();

  return (
    <>
      {items.map((item) => {
        if (item.kind === "trigger") {
          return (
            <div key="trigger">
              <TriggerCard item={item} />
            </div>
          );
        }

        const connector = (
          <InsertAffordance
            edgeId={item.incomingEdgeId}
            onOpenPalette={onOpenPalette}
            disabled={readOnly}
          />
        );

        if (item.kind === "step") {
          return (
            <div key={item.node.node_id}>
              {connector}
              <StepCard node={item.node} />
            </div>
          );
        }

        if (item.kind === "condition") {
          return (
            <div key={item.node.node_id}>
              {connector}
              <ConditionCard item={item} />
            </div>
          );
        }

        return (
          <div key={item.node.node_id}>
            {connector}
            <EndCard node={item.node} />
          </div>
        );
      })}
    </>
  );
}
