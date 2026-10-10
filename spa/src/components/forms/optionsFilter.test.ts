import { describe, expect, it } from "vitest";

import type { FormInput } from "../../types/form";
import { applyFieldChange, withFilteredOptions } from "./optionsFilter";

const provider: FormInput = {
  input_type: "select",
  name: "agent_provider",
  label: "Provider",
  options: [
    { value: "OpenAI", label: "OpenAI" },
    { value: "OpenAIAPI", label: "OpenAIAPI" },
  ],
};

const model: FormInput = {
  input_type: "search",
  name: "agent_model",
  label: "Model",
  options_filter: { field: "agent_provider" },
  options: [
    { value: "gpt-5.5", label: "[OpenAI] gpt-5.5", group: "OpenAI" },
    { value: "gpt-5.5", label: "[OpenAI API] gpt-5.5", group: "OpenAIAPI" },
    { value: "gpt-4.1", label: "[OpenAI API] gpt-4.1", group: "OpenAIAPI" },
    { value: "default", label: "Provider default" },
  ],
};

describe("withFilteredOptions", () => {
  it("offers only the chosen provider's models, so equal ids from two providers never meet", () => {
    const labels = withFilteredOptions(model, { agent_provider: "OpenAIAPI" }).options?.map((o) => o.label);

    expect(labels).toEqual(["[OpenAI API] gpt-5.5", "[OpenAI API] gpt-4.1", "Provider default"]);
  });

  it("offers only ungrouped options until a provider is chosen", () => {
    expect(withFilteredOptions(model, { agent_provider: "" }).options?.map((o) => o.value)).toEqual(["default"]);
  });

  it("leaves fields without a filter untouched", () => {
    expect(withFilteredOptions(provider, {})).toBe(provider);
  });
});

describe("applyFieldChange", () => {
  const fields = [provider, model];

  it("clears the model when the provider changes", () => {
    const next = applyFieldChange(fields, { agent_provider: "OpenAI", agent_model: "gpt-5.5" }, "agent_provider", "OpenAIAPI");

    expect(next).toEqual({ agent_provider: "OpenAIAPI", agent_model: "" });
  });

  it("keeps the model when the same provider is picked again", () => {
    const next = applyFieldChange(fields, { agent_provider: "OpenAI", agent_model: "gpt-5.5" }, "agent_provider", "OpenAI");

    expect(next.agent_model).toBe("gpt-5.5");
  });

  it("changes only the edited field otherwise", () => {
    const next = applyFieldChange(fields, { agent_provider: "OpenAI", agent_model: "" }, "agent_model", "gpt-5.5");

    expect(next).toEqual({ agent_provider: "OpenAI", agent_model: "gpt-5.5" });
  });
});
