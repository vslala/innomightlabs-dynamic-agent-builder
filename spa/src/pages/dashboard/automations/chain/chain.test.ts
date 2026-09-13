import { describe, expect, it } from "vitest";

import type {
  AutomationActionCatalogItem,
  AutomationEdge,
  AutomationGraphResponse,
  AutomationNode,
  AutomationNodeType,
  AutomationTrigger,
} from "../../../../types/automation";
import {
  type Chain,
  findJoin,
  flattenSteps,
  groupOutgoing,
  isChainEditable,
  linearize,
  tailEdgeId,
  topoOrder,
} from "./chainModel";
import {
  canMoveStep,
  convertStepType,
  deleteStep,
  ensureChainSkeleton,
  insertStepOnEdge,
  moveStep,
  patchStep,
  stopLane,
} from "./chainOperations";
import { validateChain } from "./chainValidation";
import { buildSmartValueGroups, detectInputKeys, eligibleSteps } from "./smartValues";
import {
  insertTokenAt,
  isUnknownPath,
  openTokenQuery,
  parseTokenPaths,
} from "../../../../components/forms/smartValueTokens";
import { describeCron, describeStep } from "./actionSummary";
import {
  compileCondition,
  describeParsedCondition,
  parseCondition,
  type StructuredCondition,
} from "./conditionExpression";

const AUTOMATION_ID = "auto-1";

function node(
  id: string,
  type: AutomationNodeType,
  overrides: Partial<AutomationNode> = {}
): AutomationNode {
  return {
    node_id: id,
    automation_id: AUTOMATION_ID,
    type,
    name: id,
    alias: type === "action" || type === "condition" ? id.replace(/-/g, "_") : null,
    description: null,
    position: {},
    config: type === "condition" ? { expression: "input.go", true_label: "true", false_label: "false" } : {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

function edge(id: string, source: string, target: string, label = "next"): AutomationEdge {
  return {
    edge_id: id,
    automation_id: AUTOMATION_ID,
    source_node_id: source,
    target_node_id: target,
    label,
    condition: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  };
}

function trigger(): AutomationTrigger {
  return {
    trigger_id: "trig-1",
    automation_id: AUTOMATION_ID,
    type: "manual",
    name: "Manual",
    enabled: true,
    entry_node_id: "start",
    config: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: null,
  };
}

function graphOf(nodes: AutomationNode[], edges: AutomationEdge[]): AutomationGraphResponse {
  return {
    automation: {
      automation_id: AUTOMATION_ID,
      title: "Test",
      description: null,
      status: "draft",
      version: 1,
      created_by: "tester@example.com",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: null,
    },
    nodes,
    edges,
    triggers: [trigger()],
  };
}

/** start -> a -> b -> final */
function linearGraph(): AutomationGraphResponse {
  return graphOf(
    [node("start", "start"), node("a", "action"), node("b", "action"), node("final", "final")],
    [edge("e1", "start", "a"), edge("e2", "a", "b"), edge("e3", "b", "final")]
  );
}

/** start -> cond -{true: t1 -> join}{false: join}-> join -> final */
function branchGraph(): AutomationGraphResponse {
  return graphOf(
    [
      node("start", "start"),
      node("cond", "condition"),
      node("t1", "action"),
      node("join", "action"),
      node("final", "final"),
    ],
    [
      edge("e1", "start", "cond"),
      edge("e2", "cond", "t1", "true"),
      edge("e3", "cond", "join", "false"),
      edge("e4", "t1", "join"),
      edge("e5", "join", "final"),
    ]
  );
}

/** start -> cond -{true: t1 -> final}{false: final straight away} */
function stopBranchGraph(): AutomationGraphResponse {
  return graphOf(
    [node("start", "start"), node("cond", "condition"), node("t1", "action"), node("final", "final")],
    [
      edge("e1", "start", "cond"),
      edge("e2", "cond", "t1", "true"),
      edge("e3", "cond", "final", "false"),
      edge("e4", "t1", "final"),
    ]
  );
}

function catalogItem(
  overrides: Partial<AutomationActionCatalogItem> = {}
): AutomationActionCatalogItem {
  return {
    action_type: "skill_action",
    skill_id: "gmail",
    installed_skill_id: "gmail:default",
    skill_name: "Gmail",
    action: "search",
    label: "Gmail: search",
    description: "Search the mailbox",
    input_schema: { required: ["query"], properties: { query: { type: "string" } } },
    action_form: {
      form_name: "Gmail search",
      submit_path: "",
      form_inputs: [
        { input_type: "text", name: "query", label: "Query" },
        { input_type: "text", name: "max_results", label: "Max results" },
      ],
    },
    available: true,
    configured: true,
    enabled: true,
    disabled_reason: null,
    install_schema: null,
    connectors: [],
    ...overrides,
  };
}

describe("linearize", () => {
  it("reads a linear graph as a trigger, its steps, and an end card", () => {
    const chain = linearize(linearGraph());
    expect(chain.items.map((item) => item.kind)).toEqual(["trigger", "step", "step", "end"]);
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual(["a", "b"]);
    expect(isChainEditable(chain)).toBe(true);
  });

  it("nests rejoining branches as lanes and continues the spine at the join", () => {
    const chain = linearize(branchGraph());
    expect(chain.items.map((item) => item.kind)).toEqual(["trigger", "condition", "step", "end"]);

    const condition = chain.items[1];
    if (condition.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes.map((lane) => lane.label)).toEqual(["true", "false"]);
    expect(condition.lanes[0].items.map((item) => item.kind === "step" && item.node.node_id)).toEqual(["t1"]);
    expect(condition.lanes[0].stops).toBe(false);
    expect(condition.lanes[1].items).toHaveLength(0);
    expect(condition.lanes[1].stops).toBe(false);

    const afterJoin = chain.items[2];
    if (afterJoin.kind !== "step") throw new Error("expected step");
    expect(afterJoin.node.node_id).toBe("join");
    expect(chain.unsupported).toEqual([]);
  });

  it("marks a lane that runs straight to the final node as a stop", () => {
    const chain = linearize(stopBranchGraph());
    const condition = chain.items[1];
    if (condition.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes[0].stops).toBe(false);
    expect(condition.lanes[1].stops).toBe(true);
    expect(chain.items.at(-1)?.kind).toBe("end");
    expect(chain.unsupported).toEqual([]);
  });

  it("handles a condition nested inside a lane", () => {
    const graph = graphOf(
      [
        node("start", "start"),
        node("outer", "condition"),
        node("inner", "condition"),
        node("deep", "action"),
        node("join", "action"),
        node("final", "final"),
      ],
      [
        edge("e1", "start", "outer"),
        edge("e2", "outer", "inner", "true"),
        edge("e3", "outer", "join", "false"),
        edge("e4", "inner", "deep", "true"),
        edge("e5", "inner", "join", "false"),
        edge("e6", "deep", "join"),
        edge("e7", "join", "final"),
      ]
    );
    const chain = linearize(graph);
    expect(chain.unsupported).toEqual([]);
    const outer = chain.items[1];
    if (outer.kind !== "condition") throw new Error("expected condition");
    const nested = outer.lanes[0].items[0];
    if (nested?.kind !== "condition") throw new Error("expected nested condition");
    expect(nested.node.node_id).toBe("inner");
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual([
      "outer",
      "inner",
      "deep",
      "join",
    ]);
  });

  it("reports fan-out as unsupported instead of dropping steps", () => {
    const graph = graphOf(
      [node("start", "start"), node("a", "action"), node("b", "action"), node("c", "action"), node("final", "final")],
      [
        edge("e1", "start", "a"),
        edge("e2", "a", "b"),
        edge("e3", "a", "c", "error"),
        edge("e4", "b", "final"),
        edge("e5", "c", "final"),
      ]
    );
    const chain = linearize(graph);
    expect(chain.unsupported).toContain("a");
    expect(isChainEditable(chain)).toBe(false);
  });

  it("reports an orphaned step as unsupported", () => {
    const graph = graphOf(
      [node("start", "start"), node("a", "action"), node("orphan", "action"), node("final", "final")],
      [edge("e1", "start", "a"), edge("e2", "a", "final")]
    );
    expect(linearize(graph).unsupported).toEqual(["orphan"]);
  });

  it("anchors the trailing add-step affordance on the edge into the end card", () => {
    expect(tailEdgeId(linearize(linearGraph()))).toBe("e3");
  });
});

describe("findJoin", () => {
  it("picks the earliest node both lanes reach", () => {
    const graph = branchGraph();
    const join = findJoin("t1", "join", groupOutgoing(graph.edges), topoOrder(graph));
    expect(join).toBe("join");
  });

  it("falls back to the final node when lanes only meet at the end", () => {
    const graph = stopBranchGraph();
    const join = findJoin("t1", "final", groupOutgoing(graph.edges), topoOrder(graph));
    expect(join).toBe("final");
  });
});

describe("insertStepOnEdge", () => {
  it("splices a step into the middle of the chain rather than appending", () => {
    const result = insertStepOnEdge(linearGraph(), "e2", "action");
    const chain = linearize(result.graph);
    const ids = flattenSteps(chain).map((step) => step.node_id);
    expect(ids).toHaveLength(3);
    expect(ids[0]).toBe("a");
    expect(ids[2]).toBe("b");
    expect(ids[1]).toBe(result.focusNodeId);
    expect(result.persist).toEqual({ kind: "structural" });
    expect(chain.unsupported).toEqual([]);
  });

  it("inserts into a branch lane using the lane edge", () => {
    const graph = branchGraph();
    const result = insertStepOnEdge(graph, "e3", "action");
    const chain = linearize(result.graph);
    const condition = chain.items[1];
    if (condition.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes[1].items).toHaveLength(1);
    expect(condition.lanes[0].items.map((item) => item.kind === "step" && item.node.node_id)).toEqual(["t1"]);
  });

  it("turns a stop lane back into a step when inserted on the stop edge", () => {
    const result = insertStepOnEdge(stopBranchGraph(), "e3", "action");
    const condition = linearize(result.graph).items[1];
    if (condition.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes[1].stops).toBe(false);
    expect(condition.lanes[1].items).toHaveLength(1);
  });

  it("gives a new condition two lanes that both rejoin, so no branch dead-ends", () => {
    const result = insertStepOnEdge(linearGraph(), "e2", "condition");
    const chain = linearize(result.graph);
    expect(chain.unsupported).toEqual([]);
    const condition = chain.items.find((item) => item.kind === "condition");
    if (condition?.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes).toHaveLength(2);
    expect(condition.lanes.every((lane) => !lane.stops)).toBe(true);
  });
});

describe("deleteStep", () => {
  it("reconnects the predecessor to the successor", () => {
    const result = deleteStep(linearGraph(), "a");
    const chain = linearize(result.graph);
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual(["b"]);
    expect(chain.unsupported).toEqual([]);
    expect(result.graph.edges.some((item) => item.source_node_id === "a")).toBe(false);
    expect(
      result.graph.edges.some((item) => item.source_node_id === "start" && item.target_node_id === "b")
    ).toBe(true);
  });

  it("keeps every remaining node reachable when deleting the last step", () => {
    const result = deleteStep(linearGraph(), "b");
    const chain = linearize(result.graph);
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual(["a"]);
    expect(chain.unsupported).toEqual([]);
  });

  it("keeps the true lane and discards only false-lane steps", () => {
    const graph = graphOf(
      [
        node("start", "start"),
        node("cond", "condition"),
        node("t1", "action"),
        node("f1", "action"),
        node("join", "action"),
        node("final", "final"),
      ],
      [
        edge("e1", "start", "cond"),
        edge("e2", "cond", "t1", "true"),
        edge("e3", "cond", "f1", "false"),
        edge("e4", "t1", "join"),
        edge("e5", "f1", "join"),
        edge("e6", "join", "final"),
      ]
    );
    const result = deleteStep(graph, "cond");
    expect(result.removedNodeIds.sort()).toEqual(["cond", "f1"]);
    const chain = linearize(result.graph);
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual(["t1", "join"]);
    expect(chain.unsupported).toEqual([]);
  });

  it("refuses to delete boundary nodes", () => {
    expect(deleteStep(linearGraph(), "start").persist).toEqual({ kind: "none" });
    expect(deleteStep(linearGraph(), "final").persist).toEqual({ kind: "none" });
  });
});

describe("moveStep", () => {
  it("swaps two adjacent steps", () => {
    expect(canMoveStep(linearGraph(), "a", "down")).toBe(true);
    const result = moveStep(linearGraph(), "a", "down");
    const chain = linearize(result.graph);
    expect(flattenSteps(chain).map((step) => step.node_id)).toEqual(["b", "a"]);
    expect(chain.unsupported).toEqual([]);
  });

  it("moves a step up to the same effect", () => {
    const result = moveStep(linearGraph(), "b", "up");
    expect(flattenSteps(linearize(result.graph)).map((step) => step.node_id)).toEqual(["b", "a"]);
  });

  it("will not move past a branch or a boundary", () => {
    expect(canMoveStep(linearGraph(), "a", "up")).toBe(false);
    expect(canMoveStep(linearGraph(), "b", "down")).toBe(false);
    expect(canMoveStep(branchGraph(), "t1", "up")).toBe(false);
  });
});

describe("convertStepType", () => {
  it("turns an action into a condition with distinct true and false edges", () => {
    const result = convertStepType(linearGraph(), "a", "condition");
    const labels = result.graph.edges
      .filter((item) => item.source_node_id === "a")
      .map((item) => item.label)
      .sort();
    expect(labels).toEqual(["false", "true"]);
    expect(linearize(result.graph).unsupported).toEqual([]);
  });

  it("collapses a condition back to a single next edge", () => {
    const result = convertStepType(branchGraph(), "cond", "action");
    const outgoing = result.graph.edges.filter((item) => item.source_node_id === "cond");
    expect(outgoing).toHaveLength(1);
    expect(outgoing[0].label).toBe("next");
    expect(linearize(result.graph).unsupported).toEqual([]);
  });
});

describe("stopLane", () => {
  it("points a lane at the final node and discards that lane's steps", () => {
    const result = stopLane(branchGraph(), "cond", "true");
    expect(result.removedNodeIds).toEqual(["t1"]);
    const chain = linearize(result.graph);
    const condition = chain.items[1];
    if (condition.kind !== "condition") throw new Error("expected condition");
    expect(condition.lanes[0].stops).toBe(true);
    expect(chain.unsupported).toEqual([]);
  });

  it("does nothing when the lane already stops", () => {
    expect(stopLane(stopBranchGraph(), "cond", "false").persist).toEqual({ kind: "none" });
  });
});

describe("patchStep", () => {
  it("persists as a single-node patch", () => {
    const result = patchStep(linearGraph(), "a", { name: "Renamed" });
    expect(result.persist).toEqual({ kind: "node", nodeId: "a", patch: { name: "Renamed" } });
    expect(result.graph.nodes.find((item) => item.node_id === "a")?.name).toBe("Renamed");
  });
});

describe("ensureChainSkeleton", () => {
  it("leaves a healthy graph untouched", () => {
    const graph = linearGraph();
    const result = ensureChainSkeleton(graph);
    expect(result.changed).toBe(false);
    expect(result.graph.nodes).toHaveLength(graph.nodes.length);
  });

  it("repairs a graph with no boundaries", () => {
    const result = ensureChainSkeleton(graphOf([], []));
    expect(result.changed).toBe(true);
    expect(result.graph.nodes.map((item) => item.type)).toEqual(["start", "final"]);
    expect(result.graph.edges).toHaveLength(1);
  });

  it("drops edges pointing at missing nodes", () => {
    const result = ensureChainSkeleton(
      graphOf([node("start", "start"), node("final", "final")], [edge("e1", "start", "ghost")])
    );
    expect(result.changed).toBe(true);
    expect(result.graph.edges).toHaveLength(1);
    expect(result.graph.edges[0].target_node_id).toBe("final");
  });
});

describe("validateChain", () => {
  it("flags a step with no action chosen", () => {
    const graph = linearGraph();
    const issues = validateChain(graph, linearize(graph), []);
    expect(issues.filter((issue) => issue.nodeId === "a")).toHaveLength(1);
    expect(issues[0].message).toContain("Choose what this step does");
  });

  it("flags a missing required argument by its form label", () => {
    const item = catalogItem();
    const graph = linearGraph();
    graph.nodes = graph.nodes.map((entry) =>
      entry.node_id === "a"
        ? {
            ...entry,
            config: {
              action_type: "skill_action",
              installed_skill_id: item.installed_skill_id,
              skill_id: item.skill_id,
              action: item.action,
              arguments: {},
            },
          }
        : entry
    );
    const issues = validateChain(graph, linearize(graph), [item]);
    expect(issues.some((issue) => issue.nodeId === "a" && issue.message === "Query is required.")).toBe(
      true
    );
  });

  it("surfaces a skill that needs setup", () => {
    const item = catalogItem({ available: false, disabled_reason: "Missing connected connectors: Gmail" });
    const graph = linearGraph();
    graph.nodes = graph.nodes.map((entry) =>
      entry.node_id === "a"
        ? {
            ...entry,
            config: {
              action_type: "skill_action",
              installed_skill_id: item.installed_skill_id,
              skill_id: item.skill_id,
              action: item.action,
              arguments: { query: "is:unread" },
            },
          }
        : entry
    );
    const issues = validateChain(graph, linearize(graph), [item]);
    expect(issues.some((issue) => issue.message.includes("Missing connected connectors"))).toBe(true);
  });

  it("flags a condition with no expression", () => {
    const graph = branchGraph();
    graph.nodes = graph.nodes.map((entry) =>
      entry.node_id === "cond" ? { ...entry, config: { expression: "  " } } : entry
    );
    const issues = validateChain(graph, linearize(graph), []);
    expect(issues.some((issue) => issue.nodeId === "cond")).toBe(true);
  });

  it("warns when no trigger is enabled", () => {
    const graph = linearGraph();
    graph.triggers = [{ ...trigger(), enabled: false }];
    const issues = validateChain(graph, linearize(graph), []);
    expect(issues.some((issue) => issue.message.includes("Every trigger is disabled"))).toBe(true);
  });
});

describe("smart values", () => {
  const context = {
    input: { topic: "inbox" },
    trigger: { type: "manual", trigger_id: "trig-1" },
    steps: {
      a: {
        node_id: "a",
        name: "a",
        type: "action",
        status: "succeeded",
        output: { result: { messages: [{ subject: "Q3 recap" }] } },
      },
    },
    execution: { last_step_alias: "a", last_node_id: "a" },
  };

  it("offers only steps that can run before the edited one", () => {
    const graph = linearGraph();
    expect(eligibleSteps(graph, "b").map((step) => step.node_id)).toEqual(["a"]);
    expect(eligibleSteps(graph, "a")).toEqual([]);
  });

  it("excludes the sibling branch of a condition", () => {
    const graph = graphOf(
      [
        node("start", "start"),
        node("cond", "condition"),
        node("t1", "action"),
        node("f1", "action"),
        node("final", "final"),
      ],
      [
        edge("e1", "start", "cond"),
        edge("e2", "cond", "t1", "true"),
        edge("e3", "cond", "f1", "false"),
        edge("e4", "t1", "final"),
        edge("e5", "f1", "final"),
      ]
    );
    expect(eligibleSteps(graph, "f1").map((step) => step.node_id)).toEqual(["cond"]);
  });

  it("builds groups with alias paths and run samples", () => {
    const graph = linearGraph();
    const groups = buildSmartValueGroups({ graph, forNodeId: "b", catalog: [], context });
    const step = groups.find((group) => group.nodeId === "a");
    expect(step?.label).toBe("a");
    expect(step?.fields.some((field) => field.path === "steps.a.output.result")).toBe(true);
    expect(
      step?.fields.find((field) => field.path === "steps.a.output.result.messages.0.subject")?.sample
    ).toBe("Q3 recap");
    expect(groups.find((group) => group.id === "input")?.fields.some((field) => field.path === "input.topic")).toBe(
      true
    );
    expect(groups.find((group) => group.id === "last")).toBeTruthy();
  });

  it("falls back to node id paths when a step has no alias", () => {
    const graph = linearGraph();
    graph.nodes = graph.nodes.map((entry) => (entry.node_id === "a" ? { ...entry, alias: null } : entry));
    const groups = buildSmartValueGroups({ graph, forNodeId: "b", catalog: [], context: null });
    const step = groups.find((group) => group.nodeId === "a");
    expect(step?.fields.every((field) => field.path.startsWith("nodes.a."))).toBe(true);
  });

  it("parses tokens and ignores filters when reporting the path", () => {
    expect(
      parseTokenPaths('Hi {{ steps.a.output.result }} and {{ input.topic | default("x") }}')
    ).toEqual(["steps.a.output.result", "input.topic"]);
  });

  it("reports the picker filter only while the caret sits in an open token", () => {
    expect(openTokenQuery("Use {{ ste")).toBe("ste");
    expect(openTokenQuery("Use {{ input.topic }} and")).toBe(null);
    expect(openTokenQuery("plain text")).toBe(null);
  });

  it("replaces a half-typed token when inserting", () => {
    const result = insertTokenAt("Use {{ inp", 10, 10, "{{ input.topic }}");
    expect(result.value).toBe("Use {{ input.topic }}");
    expect(result.cursor).toBe(result.value.length);
  });

  it("inserts over a selection", () => {
    const result = insertTokenAt("Use OLD here", 4, 7, "{{ input.topic }}");
    expect(result.value).toBe("Use {{ input.topic }} here");
  });

  it("detects manual input keys used anywhere in the graph", () => {
    const graph = linearGraph();
    graph.nodes = graph.nodes.map((entry) =>
      entry.node_id === "a"
        ? { ...entry, config: { arguments: { query: "{{ input.mailbox }} and {{ $.input.since }}" } } }
        : entry
    );
    expect(detectInputKeys(graph)).toEqual(["mailbox", "since"]);
  });

  it("flags tokens whose reference no longer exists", () => {
    const graph = linearGraph();
    const groups = buildSmartValueGroups({ graph, forNodeId: "b", catalog: [], context });
    expect(isUnknownPath("steps.a.output.result", groups)).toBe(false);
    expect(isUnknownPath("steps.gone.output.result", groups)).toBe(true);
    // Legacy JSON-context paths still resolve server-side.
    expect(isUnknownPath("$.legacy.path", groups)).toBe(false);
  });
});

describe("condition expressions", () => {
  it("compiles the shapes the runner understands", () => {
    expect(compileCondition({ kind: "structured", left: "steps.a.output.result", operator: "truthy", right: "" })).toBe(
      "steps.a.output.result"
    );
    expect(compileCondition({ kind: "structured", left: "steps.a.status", operator: "eq", right: "succeeded" })).toBe(
      'steps.a.status == "succeeded"'
    );
    expect(compileCondition({ kind: "structured", left: "input.plan", operator: "ne", right: "free" })).toBe(
      'input.plan != "free"'
    );
    expect(compileCondition({ kind: "structured", left: "input.count", operator: "eq", right: "3" })).toBe(
      "input.count == 3"
    );
    expect(compileCondition({ kind: "structured", left: "", operator: "truthy", right: "" })).toBe("");
  });

  it("round-trips through the parser", () => {
    const cases: StructuredCondition[] = [
      { kind: "structured", left: "steps.a.output.result", operator: "truthy", right: "" },
      { kind: "structured", left: "steps.a.status", operator: "eq", right: "succeeded" },
      { kind: "structured", left: "input.plan", operator: "ne", right: "free" },
    ];
    cases.forEach((condition) => {
      expect(parseCondition(compileCondition(condition))).toEqual(condition);
    });
  });

  it("parses legacy and hand-written expressions", () => {
    expect(parseCondition("$.input.plan == 'pro'")).toEqual({
      kind: "structured",
      left: "$.input.plan",
      operator: "eq",
      right: "pro",
    });
    expect(parseCondition("count(x) > 2").kind).toBe("raw");
    expect(parseCondition("")).toEqual({ kind: "structured", left: "", operator: "truthy", right: "" });
  });

  it("keeps a comparison operator inside a quoted value intact", () => {
    expect(parseCondition('steps.a.output.text == "a == b"')).toEqual({
      kind: "structured",
      left: "steps.a.output.text",
      operator: "eq",
      right: "a == b",
    });
  });

  it("describes a condition for the collapsed card", () => {
    expect(describeParsedCondition("steps.a.status == 'succeeded'")).toBe(
      "steps.a.status is equal to succeeded"
    );
    expect(describeParsedCondition("steps.a.output.result")).toBe("steps.a.output.result has a value");
    expect(describeParsedCondition("")).toBe(null);
  });
});

describe("summaries", () => {
  it("describes a configured action with its primary argument", () => {
    const item = catalogItem();
    const step = node("a", "action", {
      name: "Find mail",
      config: {
        action_type: "skill_action",
        installed_skill_id: item.installed_skill_id,
        skill_id: item.skill_id,
        action: item.action,
        arguments: { query: "is:unread", max_results: "50" },
      },
    });
    const summary = describeStep(step, [item]);
    expect(summary.kind).toBe("then");
    expect(summary.icon).toBe("email");
    expect(summary.title).toBe("Find mail");
    expect(summary.subtitle).toBe("Gmail: search · is:unread");
  });

  it("describes an unconfigured action", () => {
    expect(describeStep(node("a", "action"), []).subtitle).toBe("No action chosen yet");
  });

  it("reads common cron shapes in plain language", () => {
    expect(describeCron("0 9 * * 1-5")).toBe("Every weekday at 09:00");
    expect(describeCron("30 6 * * *")).toBe("Every day at 06:30");
    expect(describeCron("0 9 * * 1")).toBe("Every Monday at 09:00");
    expect(describeCron("*/5 * * * *")).toBe("*/5 * * * *");
  });
});

describe("chain round trip", () => {
  const operations: Array<[string, (graph: AutomationGraphResponse) => AutomationGraphResponse]> = [
    ["insert action mid-chain", (graph) => insertStepOnEdge(graph, "e2", "action").graph],
    ["insert condition mid-chain", (graph) => insertStepOnEdge(graph, "e2", "condition").graph],
    ["delete first step", (graph) => deleteStep(graph, "a").graph],
    ["move step down", (graph) => moveStep(graph, "a", "down").graph],
    ["convert to condition", (graph) => convertStepType(graph, "a", "condition").graph],
  ];

  operations.forEach(([name, apply]) => {
    it(`keeps the graph expressible after: ${name}`, () => {
      const chain: Chain = linearize(apply(linearGraph()));
      expect(chain.unsupported).toEqual([]);
      expect(chain.items[0].kind).toBe("trigger");
      expect(chain.items.at(-1)?.kind).toBe("end");
    });
  });
});
