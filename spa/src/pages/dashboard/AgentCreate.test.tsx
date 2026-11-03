import * as React from "react";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { AgentCreate } from "./AgentCreate";
import { SchemaForm } from "../../components/forms";
import { agentApiService } from "../../services/agents/AgentApiService";
import { HttpError } from "../../services/http/client";
import type { FormSchema } from "../../types/form";

const hooks = vi.hoisted(() => ({ values: [] as unknown[], cursor: 0, navigate: vi.fn() }));
vi.mock("react", async (load) => ({
  ...await load<typeof import("react")>(),
  useEffect: vi.fn(),
  useState: (initial: unknown) => {
    const index = hooks.cursor++;
    if (!(index in hooks.values)) hooks.values[index] = initial;
    return [hooks.values[index], (value: unknown) => { hooks.values[index] = value; }];
  },
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => hooks.navigate }));
vi.mock("../../services/agents/AgentApiService", () => ({ agentApiService: { createAgent: vi.fn() } }));

const schema: FormSchema = { form_name: "create", submit_path: "/agents", form_inputs: [] };
function page() { hooks.cursor = 0; return AgentCreate(); }
function find<P>(node: React.ReactNode, matches: (element: React.ReactElement<P>) => boolean): React.ReactElement<P> | undefined {
  if (!React.isValidElement<P & { children?: React.ReactNode }>(node)) return undefined;
  if (matches(node)) return node;
  for (const child of React.Children.toArray(node.props.children)) {
    const match = find(child, matches);
    if (match) return match;
  }
}
function form() {
  const element = find<React.ComponentProps<typeof SchemaForm>>(page(), (node) => node.type === SchemaForm);
  if (!element) throw new Error("Missing agent form");
  return element;
}
function alert() {
  return find<{ role?: string; children?: React.ReactNode }>(page(), (node) => node.props.role === "alert");
}
beforeEach(() => {
  hooks.values = [schema, false, null, false];
  hooks.cursor = 0;
  hooks.navigate.mockReset();
  vi.mocked(agentApiService.createAgent).mockReset();
  vi.spyOn(console, "error").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe("agent creation errors", () => {
  it.each([
    [new HttpError(429, "Agent limit reached (3). Upgrade to create more."), "Agent limit reached (3). Upgrade to create more."],
    [new HttpError(400, "Choose an available model."), "Choose an available model."],
    [new HttpError(403, "private policy details"), "You don't have permission to create an agent in this account. Ask an account administrator for access."],
    [new HttpError(0, "offline"), "Network error. Check your connection and try again."],
    [new HttpError(500, "private traceback"), "Failed to create agent. Please try again."],
    [new Error("private detail"), "Failed to create agent. Please try again."],
    [new HttpError(429, "Request failed"), "Failed to create agent. Please try again."],
    [new HttpError(400, "  "), "Failed to create agent. Please try again."],
  ])("shows a safe, actionable message for %s", async (error, message) => {
    vi.mocked(agentApiService.createAgent).mockRejectedValue(error);
    const initialForm = form();
    await initialForm.props.onSubmit({ agent_name: "My draft" });
    expect(alert()?.props.children).toBe(message);
    expect(hooks.navigate).not.toHaveBeenCalled();
    expect(form().props.isLoading).toBe(false);
    expect(form().props.schema).toBe(schema);
    expect(form().type).toBe(initialForm.type);
    expect(form().key).toBe(initialForm.key);
  });

  it("shows pending state, clears the old error, and recovers after a quota rejection", async () => {
    let rejectRequest!: (error: unknown) => void;
    vi.mocked(agentApiService.createAgent).mockReturnValue(new Promise((_, reject) => { rejectRequest = reject; }));
    hooks.values[2] = "Old error";
    const submitted = form().props.onSubmit({ agent_name: "Draft" });
    expect(form().props.isLoading).toBe(true);
    expect(alert()).toBeUndefined();
    rejectRequest(new HttpError(429, "Agent limit reached."));
    await submitted;
    expect(form().props.isLoading).toBe(false);
    expect(alert()?.props.children).toBe("Agent limit reached.");
  });

  it("submits entered values and navigates only after success", async () => {
    vi.mocked(agentApiService.createAgent).mockResolvedValue({} as Awaited<ReturnType<typeof agentApiService.createAgent>>);
    await form().props.onSubmit({ agent_name: "My draft", agent_model: "model-1" });
    expect(agentApiService.createAgent).toHaveBeenCalledExactlyOnceWith({ agent_name: "My draft", agent_model: "model-1" });
    expect(hooks.navigate).toHaveBeenCalledExactlyOnceWith("/dashboard/agents");
    expect(hooks.values[3]).toBe(false);
  });
});
