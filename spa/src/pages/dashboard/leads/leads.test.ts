import { describe, expect, it } from "vitest";
import type { Capture } from "../../../types/leads";
import { answerText, captureHeadline, filtersFromSearch, macroFor, searchFromFilters, slugFrom } from "./leads";

const capture: Capture = {
  capture_id: "c1",
  account_id: "a1",
  form_name: "Damage claim",
  form_inputs: [
    { input_type: "text", name: "name", label: "Name" },
    { input_type: "text", name: "email", label: "Email", validation: { format: "email" } },
    { input_type: "choice", name: "rooms", label: "Rooms", values: ["Kitchen", "Hall"], attr: { variant: "checkbox" } },
    { input_type: "file_upload", name: "evidence", label: "Photos" },
  ],
  answers: { name: "Jane", rooms: ["Kitchen", "Hall"], evidence: ["f1", "f-gone"] },
  files: [{ file_id: "f1", input_name: "evidence", filename: "dent.png", content_type: "image/png", size_bytes: 10 }],
  agent_id: "agent-1",
  actor_kind: "visitor",
  actor_id: "v1",
  source: "widget",
  status: "new",
  created_at: "2026-10-15T10:00:00+00:00",
};

describe("leads helpers", () => {
  it("write the macro an agent's instructions use", () => {
    expect(macroFor("demo-request")).toBe("{{ lead_form:demo-request }}");
  });

  it("make a slug from a form's name", () => {
    expect(slugFrom("Book a Demo!")).toBe("book-a-demo");
    expect(slugFrom("  Claims / 2026 ")).toBe("claims-2026");
  });

  it("show answers as text, uploads by name", () => {
    const [, email, rooms, evidence] = capture.form_inputs;
    expect(answerText(capture, rooms)).toBe("Kitchen, Hall");
    expect(answerText(capture, evidence)).toBe("dent.png, f-gone");
    expect(answerText(capture, email)).toBe("");
  });

  it("headline a lead by email, else its first answer", () => {
    expect(captureHeadline(capture)).toBe("Jane");
    expect(captureHeadline({ ...capture, answers: { ...capture.answers, email: "jane@acme.com" } })).toBe("jane@acme.com");
    expect(captureHeadline({ ...capture, answers: {} })).toBe("No answers");
  });

  it("keep filters in the URL", () => {
    const filters = { agent_id: "agent-1", form: "claim", include_tests: true };
    expect(filtersFromSearch(searchFromFilters(filters))).toEqual(filters);
    expect(searchFromFilters({}).toString()).toBe("");
  });
});
