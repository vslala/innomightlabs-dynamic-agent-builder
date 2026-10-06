import type {
  MCPAudience,
  MCPCatalogTool,
  MCPSharingSummary,
  MCPSharingView,
  UpdateMCPSharingRequest,
} from "../../../../types/connectors";
import { SHAREABLE_AUDIENCES } from "../audiences";

export type ToolRisk = "read" | "write" | "destructive";

export interface ToolGroup {
  risk: ToolRisk;
  tools: MCPCatalogTool[];
}

/** What the owner is choosing in the share dialog, before it is saved. */
export interface SharingDraft {
  audiences: MCPAudience[];
  tools: string[];
  accepted: boolean;
}

const RISK_ORDER: ToolRisk[] = ["read", "write", "destructive"];

export function toolRisk(tool: MCPCatalogTool): ToolRisk {
  if (tool.read_only) return "read";
  return tool.destructive ? "destructive" : "write";
}

export function isShared(view: MCPSharingView): boolean {
  return view.sharing.available_to.length > 0;
}

/** Shared tools the server no longer offers. They are dropped on save, and the owner is told so. */
export function retiredTools(view: MCPSharingView): string[] {
  const offered = new Set(view.catalog?.tools.map((tool) => tool.name));
  return view.sharing.allowed_tools.filter((name) => !offered.has(name));
}

/** A first share starts from the read-only tools; nothing that can change data is ever pre-selected. */
export function initialDraft(view: MCPSharingView): SharingDraft {
  const tools = view.catalog?.tools ?? [];
  if (!isShared(view)) {
    return {
      audiences: [],
      tools: tools.filter((tool) => toolRisk(tool) === "read").map((tool) => tool.name),
      accepted: false,
    };
  }
  const offered = new Set(tools.map((tool) => tool.name));
  return {
    audiences: view.sharing.available_to,
    tools: view.sharing.allowed_tools.filter((name) => offered.has(name)),
    accepted: false,
  };
}

export function groupTools(tools: MCPCatalogTool[], query: string): ToolGroup[] {
  const needle = query.trim().toLowerCase();
  const matching = tools.filter((tool) =>
    [tool.name, tool.title ?? "", tool.description].some((text) => text.toLowerCase().includes(needle))
  );
  return RISK_ORDER.map((risk) => ({ risk, tools: matching.filter((tool) => toolRisk(tool) === risk) })).filter(
    (group) => group.tools.length > 0
  );
}

export function toggled<T>(items: T[], item: T): T[] {
  return items.includes(item) ? items.filter((existing) => existing !== item) : [...items, item];
}

/** Sharing needs an audience, a tool and the owner's consent. Choosing nobody stops sharing. */
export function canSave(draft: SharingDraft, view: MCPSharingView): boolean {
  if (draft.audiences.length === 0) return isShared(view);
  return draft.tools.length > 0 && draft.accepted;
}

export function toRequest(draft: SharingDraft, view: MCPSharingView): UpdateMCPSharingRequest {
  if (draft.audiences.length === 0) return { available_to: [], allowed_tools: [] };
  return {
    available_to: draft.audiences,
    allowed_tools: draft.tools,
    accept_disclaimer_version: view.disclaimer.version,
  };
}

export function sharingLabel(summary: MCPSharingSummary): string {
  if (summary.available_to.length === 0) return "Only you";
  const audiences = SHAREABLE_AUDIENCES.filter(({ kind }) => summary.available_to.includes(kind)).map(
    ({ label }) => label
  );
  const tools = summary.allowed_tool_count === 1 ? "1 tool" : `${summary.allowed_tool_count} tools`;
  return `${audiences.join(" · ")} — ${tools}`;
}
