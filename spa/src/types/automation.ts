export type AutomationStatus = "draft" | "active" | "disabled" | "deleted";
export type AutomationNodeType = "start" | "action" | "condition" | "final";
export type AutomationActionType = "invoke_agent" | "send_email" | "webhook_call";
export type AutomationTriggerType = "manual" | "webhook" | "schedule";
export type AutomationRunStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";
export type AutomationNodeRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type AutomationEdgeLabel = "next" | "true" | "false" | "error" | string;

export interface AutomationResponse {
  automation_id: string;
  title: string;
  description?: string | null;
  status: AutomationStatus;
  version: number;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

export interface AutomationNodePosition {
  x?: number;
  y?: number;
  [key: string]: unknown;
}

export interface AutomationNode {
  node_id: string;
  automation_id: string;
  type: AutomationNodeType;
  name: string;
  description?: string | null;
  position: AutomationNodePosition;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
}

export interface AutomationEdge {
  edge_id: string;
  automation_id: string;
  source_node_id: string;
  target_node_id: string;
  label: AutomationEdgeLabel;
  condition?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface AutomationTrigger {
  trigger_id: string;
  automation_id: string;
  type: AutomationTriggerType;
  name: string;
  enabled: boolean;
  entry_node_id: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
}

export interface AutomationGraphResponse {
  automation: AutomationResponse;
  nodes: AutomationNode[];
  edges: AutomationEdge[];
  triggers: AutomationTrigger[];
}

export interface InvokeAgentActionConfig {
  action_type: "invoke_agent";
  agent_id: string;
  prompt_template: string;
  input: Record<string, unknown>;
}

export interface ConditionNodeConfig {
  expression: string;
  true_label: "true";
  false_label: "false";
}

export interface CreateAutomationRequest {
  title: string;
  description?: string | null;
  status?: AutomationStatus;
}

export interface UpdateAutomationRequest {
  title?: string;
  description?: string | null;
  status?: AutomationStatus;
}

export interface CreateAutomationNodeRequest {
  node_id?: string | null;
  type: AutomationNodeType;
  name: string;
  description?: string | null;
  position?: AutomationNodePosition;
  config?: Record<string, unknown>;
}

export interface CreateAutomationEdgeRequest {
  edge_id?: string | null;
  source_node_id: string;
  target_node_id: string;
  label?: AutomationEdgeLabel;
  condition?: string | null;
}

export interface CreateAutomationTriggerRequest {
  trigger_id?: string | null;
  type: AutomationTriggerType;
  name: string;
  enabled?: boolean;
  entry_node_id: string;
  config?: Record<string, unknown>;
}

export interface SaveAutomationGraphRequest {
  nodes: CreateAutomationNodeRequest[];
  edges: CreateAutomationEdgeRequest[];
  triggers: CreateAutomationTriggerRequest[];
}

export interface StartAutomationRunRequest {
  trigger_id?: string | null;
  input: Record<string, unknown>;
}

export interface AutomationRunResponse {
  run_id: string;
  automation_id: string;
  trigger_id?: string | null;
  conversation_id?: string | null;
  status: AutomationRunStatus;
  error?: string | null;
  created_by: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface AutomationRunNodeResult {
  result_id: string;
  run_id: string;
  automation_id: string;
  node_id: string;
  status: AutomationNodeRunStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error?: string | null;
  message_ids: Record<string, string>;
  started_at: string;
  completed_at?: string | null;
}

export interface AutomationRunDetailResponse {
  run: AutomationRunResponse;
  context: Record<string, unknown>;
  node_results: AutomationRunNodeResult[];
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor?: string | null;
  has_more: boolean;
}
