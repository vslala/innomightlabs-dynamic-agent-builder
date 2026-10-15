import { describe, expect, it } from "vitest";
import type { FormInput } from "../../types/form";
import { inputNameFrom, kindById, kindOf, withAttr, withOptional } from "./formInputKinds";

const email: FormInput = {
  input_type: "text",
  name: "email",
  label: "Work email",
  validation: { format: "email" },
  attr: { help_text: "We reply here", optional: "true" },
};

describe("form input kinds", () => {
  it("recognise every kind the editor offers", () => {
    expect(kindOf(email).id).toBe("email");
    expect(kindOf({ input_type: "text", name: "n", label: "Name" }).id).toBe("text");
    expect(kindOf({ input_type: "text_area", name: "n", label: "Notes" }).id).toBe("long_text");
    expect(kindOf({ input_type: "select", name: "s", label: "Size", values: ["S", "M"] }).id).toBe("select");
    expect(kindOf({ input_type: "choice", name: "c", label: "One", values: ["a", "b"] }).id).toBe("radio");
    expect(kindOf({ input_type: "choice", name: "c", label: "Many", values: ["a", "b"], attr: { variant: "checkbox" } }).id)
      .toBe("checkboxes");
    expect(kindOf({ input_type: "choice", name: "c", label: "I agree", values: ["yes"], attr: { variant: "checkbox" } }).id)
      .toBe("consent");
    expect(kindOf({ input_type: "file_upload", name: "f", label: "Photo" }).id).toBe("file");
  });

  it("reshape an input and keep its words, dropping what the old kind needed", () => {
    const phone = kindById("phone").shape(email);
    expect(phone).toEqual({
      input_type: "text",
      name: "email",
      label: "Work email",
      attr: { help_text: "We reply here", optional: "true" },
      validation: { format: "phone" },
    });

    const picked = kindById("checkboxes").shape({ input_type: "select", name: "size", label: "Size", values: ["S", "M"] });
    expect(picked.options).toEqual([{ value: "S", label: "S" }, { value: "M", label: "M" }]);
    expect(picked.attr).toEqual({ variant: "checkbox" });
    expect(kindOf(picked).id).toBe("checkboxes");

    const consent = kindById("consent").shape(picked);
    expect(consent.values).toEqual(["yes"]);
    expect(consent.options).toBeUndefined();
    expect(kindOf(consent).id).toBe("consent");
  });

  it("start a new option list when an input had none", () => {
    expect(kindById("select").shape({ input_type: "text", name: "n", label: "Name" }).options).toEqual([
      { value: "Option 1", label: "Option 1" },
    ]);
  });

  it("derive a field name from its label", () => {
    expect(inputNameFrom("Work email")).toBe("work_email");
    expect(inputNameFrom("  2nd phone #! ")).toBe("nd_phone");
    expect(inputNameFrom("!!!")).toBe("field");
  });

  it("set and clear attributes", () => {
    expect(withOptional(email, false).attr).toEqual({ help_text: "We reply here" });
    expect(withAttr({ input_type: "text", name: "n", label: "N" }, "agent_hint", "Ask late").attr).toEqual({
      agent_hint: "Ask late",
    });
    expect(withAttr({ input_type: "text", name: "n", label: "N", attr: { agent_hint: "x" } }, "agent_hint", "").attr)
      .toBeNull();
  });
});
