import { describe, expect, it } from "vitest";
import { issueLocation, resourceLink, toParams } from "./blueprintView";

describe("blueprint view helpers", () => {
  it("keeps only text values as params", () => {
    expect(toParams({ site_url: "https://acme.example", labels: { a: "b" }, file: null })).toEqual({
      site_url: "https://acme.example",
    });
  });

  it("locates issues by line and path", () => {
    expect(issueLocation({ path: "resources.widget.agent", message: "x", line: 41 })).toBe("Line 41 · resources.widget.agent");
    expect(issueLocation({ path: "", message: "x" })).toBe("blueprint");
  });

  it("links agents and knowledge bases, not keys", () => {
    expect(resourceLink("Agent", "a1")).toBe("/dashboard/agents/a1");
    expect(resourceLink("KnowledgeBase", "k1")).toBe("/dashboard/knowledge-bases/k1");
    expect(resourceLink("WidgetKey", "w1")).toBeNull();
  });
});
