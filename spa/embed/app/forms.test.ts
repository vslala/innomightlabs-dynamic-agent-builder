import { describe, expect, it } from "vitest";

import { parseFormSubmission } from "../../src/components/chat/submittedFormParser";
import type { AgentForm } from "./api";
import { choiceVariant, collectAnswers, formatSubmission } from "./forms";

const form: AgentForm = {
  form_name: "Contact details",
  form_inputs: [
    { input_type: "text", name: "name", label: "Name" },
    { input_type: "text_area", name: "notes", label: "Notes" },
    { input_type: "text", name: "phone", label: "Phone" },
  ],
};

describe("form submissions", () => {
  it("keeps non-empty answers in form order", () => {
    expect(collectAnswers(form, { phone: "", notes: " Call me\nlater ", name: "Ada" })).toEqual([
      { fieldId: "name", label: "Name", value: "Ada" },
      { fieldId: "notes", label: "Notes", value: "Call me\nlater" },
    ]);
  });

  it("formats answers the way the dashboard parses them", () => {
    const content = formatSubmission(form, collectAnswers(form, { name: "Ada", notes: "Hi" }));

    expect(content).toContain('- name="Ada"');
    expect(parseFormSubmission(content)).toEqual({
      label: "Contact details",
      answers: [
        { label: "Name", value: "Ada" },
        { label: "Notes", value: "Hi" },
      ],
    });
  });

  it("picks a control for choice inputs", () => {
    expect(choiceVariant({ input_type: "choice", name: "ok", label: "OK", values: ["yes"] })).toBe("single-checkbox");
    expect(choiceVariant({ input_type: "choice", name: "size", label: "Size", values: ["S", "M"] })).toBe("radio");
    expect(
      choiceVariant({ input_type: "choice", name: "tags", label: "Tags", values: ["a", "b"], attr: { variant: "checkbox" } })
    ).toBe("checkboxes");
  });
});
