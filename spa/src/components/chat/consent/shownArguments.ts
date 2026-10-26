import type { ConsentBlock } from "../../../types/consent";

/** The editable arguments a set of blocks shows, so the card offers Edit only when there is something to edit. */
export function shownArguments(blocks: ConsentBlock[]): Set<string> {
  const shown = new Set<string>();
  for (const block of blocks) {
    if (block.kind === "text" && block.argument) shown.add(block.argument);
    if (block.kind === "fields") block.items.forEach((item) => item.argument && shown.add(item.argument));
    if (block.kind === "email") Object.values(block.arguments).forEach((argument) => argument && shown.add(argument));
    if (block.kind === "grants") shown.add(block.argument);
  }
  return shown;
}
