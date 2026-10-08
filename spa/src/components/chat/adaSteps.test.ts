import { describe, expect, it } from "vitest";
import type { ToolActivity } from "../../types/message";
import { adaStep } from "./adaSteps";

function activity(tool_name: string, status: ToolActivity["status"]): ToolActivity {
  return { id: tool_name, timestamp: new Date(), tool_name, status, content: "" };
}

describe("what Ada is doing", () => {
  it("names the running tool's step", () => {
    expect(adaStep([activity("plan_blueprint", "running")], true)).toBe("drafting");
    expect(adaStep([activity("show_form", "success"), activity("apply_blueprint", "running")], true)).toBe("building");
  });

  it("is thinking between tools, and quiet once the turn ends", () => {
    expect(adaStep([activity("plan_blueprint", "success")], true)).toBe("thinking");
    expect(adaStep([], true)).toBe("thinking");
    expect(adaStep([activity("plan_blueprint", "success")], false)).toBeNull();
  });
});
