import type { MCPAudience } from "../../../types/connectors";

/** Who besides the owner can be given a skill or an MCP connector, in the order we show them. */
export const SHAREABLE_AUDIENCES: { kind: MCPAudience; label: string; reach: string }[] = [
  { kind: "visitor", label: "Widget visitors", reach: "Anyone on your website, signed in or not" },
  { kind: "api", label: "API keys", reach: "Apps calling this agent with a secret key" },
  { kind: "a2a", label: "A2A agents", reach: "Other agents holding one of its A2A keys" },
];
