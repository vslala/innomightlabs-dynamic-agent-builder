import { createElement } from "react";
import { getAgentIcon } from "../lib/agentIcons";

/** The agent's icon as an element, so callers don't build a component during render. */
export function AgentIcon({ name, className }: { name: string | null | undefined; className?: string }) {
  return createElement(getAgentIcon(name), { className });
}
