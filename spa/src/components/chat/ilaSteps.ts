import type { ToolActivity } from "../../types/message";

export type IlaStep = "thinking" | "asking" | "drafting" | "building" | "checking";

export interface IlaStepCopy {
  title: string;
  detail: string;
}

/** What Ila is doing, in her words, for each of her tools (api/src/builder/tools.py). */
export const ILA_STEPS: Record<IlaStep, IlaStepCopy> = {
  thinking: { title: "Thinking it through", detail: "Working out what you need" },
  asking: { title: "Preparing a few questions", detail: "So the build fits you" },
  drafting: { title: "Drafting your blueprint", detail: "Sketching it and checking it against your account" },
  building: { title: "Building it", detail: "Creating your knowledge base, agent and widget" },
  checking: { title: "Checking on your build", detail: "Seeing how far the website reading has got" },
};

const TOOL_STEPS: Record<string, IlaStep> = {
  show_form: "asking",
  plan_blueprint: "drafting",
  apply_blueprint: "building",
  get_build_status: "checking",
};

/** The step to show while a turn runs: the latest tool still running, else "thinking"; nothing once idle. */
export function ilaStep(activities: ToolActivity[], turnRunning: boolean): IlaStep | null {
  const running = [...activities].reverse().find((activity) => activity.status === "running");
  if (running) return TOOL_STEPS[running.tool_name] ?? "thinking";
  return turnRunning ? "thinking" : null;
}
