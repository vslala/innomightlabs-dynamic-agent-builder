import { Plus } from "lucide-react";

import { Button } from "../../../../components/ui";

/**
 * The connector between two cards, which doubles as the insert point.
 *
 * Insertion is anchored on the edge rather than on a node, so adding a step
 * between two cards -- or into a branch lane -- is the same operation.
 */
export function InsertAffordance({
  edgeId,
  onOpenPalette,
  disabled = false,
  label = "Add a step here",
}: {
  edgeId: string | null;
  onOpenPalette: (edgeId: string) => void;
  disabled?: boolean;
  label?: string;
}) {
  if (!edgeId) return <div className="chain-connector chain-connector--plain" aria-hidden="true" />;

  return (
    <div className="chain-connector">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="chain-connector__button"
        onClick={() => onOpenPalette(edgeId)}
        disabled={disabled}
        title={label}
        aria-label={label}
      >
        <Plus className="h-4 w-4" />
      </Button>
    </div>
  );
}
