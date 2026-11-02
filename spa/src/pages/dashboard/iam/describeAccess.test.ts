import { describe, expect, it } from "vitest";
import type { ActionAccess, PolicySummary, Reach, ServiceAccess } from "../../../services/iam";
import { accessLines, attachable, sourceLabel } from "./describeAccess";

const summary = (policy: string, name = policy): PolicySummary => ({
  policy, name, description: "", builtin: !policy.startsWith("custom:"), attachment_count: 0,
});
const nowhere: Reach = { scope: null, resources: [], policies: [] };
const action = (verb: string, level: ActionAccess["level"], allow: Partial<Reach> = {}, deny: Partial<Reach> = {}): ActionAccess => ({
  action: `agents:${verb}`, verb, level, allow: { ...nowhere, ...allow }, deny: { ...nowhere, ...deny },
});
const service = (...actions: ActionAccess[]): ServiceAccess => ({
  service: "agents", label: "Agents", summary: "", level: "limited", actions,
});

describe("describing a member's access", () => {
  it.each([
    ["implicit", "Applies to every member"],
    ["account owner", "Account owner"],
    ["direct", "Attached directly"],
    ["group:g1", "From the group Support team"],
    ["group:gone", "From a group"],
  ])("labels the source %s", (source, label) => {
    expect(sourceLabel(source, new Map([["g1", "Support team"]]))).toBe(label);
  });

  it("offers only policies not yet attached, and never the implicit OwnerAccess", () => {
    const policies = [summary("OwnerAccess"), summary("MemberAccess"), summary("AdministratorAccess"), summary("custom:p1", "Support")];
    expect(attachable(policies, [{ policy: "MemberAccess", name: "MemberAccess" }]).map((p) => p.policy))
      .toEqual(["AdministratorAccess", "custom:p1"]);
  });

  it("groups a service's verbs by how far they reach, allowed first and denied last", () => {
    const lines = accessLines(service(
      action("Delete", "denied", {}, { scope: "all" }),
      action("Create", "all", { scope: "all" }),
      action("Get", "own", { scope: "own" }),
      action("List", "all", { scope: "all" }),
      action("Chat", "some", { scope: "some", resources: ["agent/a1", "agent/b2"] }),
      action("Update", "own", { scope: "own" }),
    ));

    expect(lines).toEqual([
      { kind: "allowed", label: "Allowed", verbs: ["Create", "List"] },
      { kind: "some", label: "Only on agent/a1, agent/b2", verbs: ["Chat"] },
      { kind: "own", label: "On what they own", verbs: ["Get", "Update"] },
      { kind: "denied", label: "Denied", verbs: ["Delete"] },
    ]);
  });

  it("shows a Deny that reaches only some resources beside what it limits", () => {
    const lines = accessLines(service(action("Delete", "all", { scope: "all" }, { scope: "some", resources: ["agent/prod"] })));

    expect(lines).toEqual([
      { kind: "allowed", label: "Allowed", verbs: ["Delete"] },
      { kind: "denied", label: "Denied on agent/prod", verbs: ["Delete"] },
    ]);
  });

  it("leaves out what nothing allows", () => {
    expect(accessLines(service(action("Create", "none")))).toEqual([]);
  });
});
