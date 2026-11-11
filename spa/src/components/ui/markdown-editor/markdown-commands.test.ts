import { describe, expect, it } from "vitest";

import { applyEdit, insertLink, toggleLinePrefix, toggleWrap } from "./markdown-commands";

describe("toggleWrap", () => {
  it("wraps the selection and keeps it selected", () => {
    const doc = "make this bold";
    const edit = toggleWrap(doc, 10, 14, "**", "bold text");

    expect(applyEdit(doc, edit)).toBe("make this **bold**");
    expect(edit.selection).toEqual({ anchor: 12, head: 16 });
  });

  it("unwraps text that is already wrapped", () => {
    const doc = "make this **bold**";
    expect(applyEdit(doc, toggleWrap(doc, 12, 16, "**", "bold text"))).toBe("make this bold");
  });

  it("inserts a selected placeholder when nothing is selected", () => {
    const edit = toggleWrap("", 0, 0, "*", "italic text");
    expect(applyEdit("", edit)).toBe("*italic text*");
    expect(edit.selection).toEqual({ anchor: 1, head: 12 });
  });
});

describe("toggleLinePrefix", () => {
  const doc = "Intro\nfirst\nsecond\nOutro";

  it("prefixes every line the selection touches", () => {
    expect(applyEdit(doc, toggleLinePrefix(doc, 7, 14, "bullet"))).toBe("Intro\n- first\n- second\nOutro");
    expect(applyEdit(doc, toggleLinePrefix(doc, 7, 14, "number"))).toBe("Intro\n1. first\n2. second\nOutro");
  });

  it("removes the prefix when every line already has it", () => {
    const listed = "Intro\n- first\n- second\nOutro";
    expect(applyEdit(listed, toggleLinePrefix(listed, 8, 18, "bullet"))).toBe(doc);
  });

  it("replaces another kind of prefix instead of stacking it", () => {
    const listed = "- first";
    expect(applyEdit(listed, toggleLinePrefix(listed, 3, 3, "heading"))).toBe("## first");
  });

  it("leaves macros and other text exactly as typed", () => {
    const text = "Collect {{ lead_form:contact_us }} snake_case *not* escaped";
    expect(applyEdit(text, toggleLinePrefix(text, 0, 0, "quote"))).toBe(`> ${text}`);
  });
});

describe("insertLink", () => {
  it("links the selection and selects the url to type over", () => {
    const doc = "see docs";
    const edit = insertLink(doc, 4, 8);
    const next = applyEdit(doc, edit);

    expect(next).toBe("see [docs](https://)");
    expect(next.slice(edit.selection.anchor, edit.selection.head)).toBe("https://");
  });
});
