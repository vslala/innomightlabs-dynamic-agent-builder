import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Capture, LeadStatus } from "../../../types/leads";
import { CaptureDetail } from "./CaptureDetail";
import styles from "./Leads.module.css";

const css = readFileSync(new URL("./Leads.module.css", import.meta.url), "utf8");

const email = "alexandra.montgomery.enterprise.partnerships@northwestern-infrastructure.example.com";
const longLabel = "Please describe the infrastructure requirements, implementation timeline, and accessibility needs for your regional teams";
const multilineAnswer = "We need a customer support agent for our regional infrastructure teams.\n\nPlease preserve the existing escalation workflow.\nTarget launch: the beginning of the next financial quarter.";
const filename = "northwestern-infrastructure-regional-support-requirements-and-implementation-plan-2026.pdf";
const statuses: LeadStatus[] = [
  { key: "new", label: "New", stage: "open" },
  { key: "qualified", label: "Qualified", stage: "open" },
];
const capture: Capture = {
  capture_id: "capture-1",
  account_id: "account-1",
  form_name: "Regional infrastructure support consultation",
  form_inputs: [
    { input_type: "text", name: "email", label: "Work email", validation: { format: "email" } },
    { input_type: "text", name: "requirements", label: longLabel },
    { input_type: "text", name: "notes", label: "Additional notes" },
    { input_type: "file_upload", name: "brief", label: "Project brief" },
  ],
  answers: { email, requirements: multilineAnswer, notes: "", brief: ["file-1"] },
  files: [{ file_id: "file-1", input_name: "brief", filename, content_type: "application/pdf", size_bytes: 48216 }],
  agent_id: "agent-1",
  conversation_id: "conversation-1",
  actor_kind: "user",
  actor_id: "user-1",
  source: "dashboard",
  status: "new",
  created_at: "2026-10-15T10:00:00+00:00",
};

function render(overrides: Partial<Capture> = {}): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <CaptureDetail
        capture={{ ...capture, ...overrides }}
        agentName="Infrastructure support agent"
        statuses={statuses}
        onChange={vi.fn()}
        onDelete={vi.fn()}
      />
    </MemoryRouter>,
  );
}

function answer(label: string, value: string): string {
  return `<div class="${styles.answer}"><dt>${label}</dt><dd>${value}</dd></div>`;
}

describe("CaptureDetail markup", () => {
  it("groups every label with its full answer, retaining long text and line breaks", () => {
    const html = render();
    expect(html).toContain(
      `<dl class="${styles.answers}">`
      + answer("Work email", email)
      + answer(longLabel, multilineAnswer)
      + answer("Additional notes", "—")
      + answer("Project brief", filename)
      + "</dl>",
    );
  });

  it.each<Capture["answers"]>([{}, { notes: "" }, { notes: [] }])("shows a placeholder for an unanswered field (%j)", (answers) => {
    expect(render({ answers })).toContain(answer("Additional notes", "—"));
  });

  it("escapes submitted answers, form labels, titles, and attachment filenames instead of rendering HTML", () => {
    const html = render({
      form_name: "<em>Consultation</em>",
      form_inputs: [{ input_type: "text", name: "message", label: "<b>Requirements</b>" }],
      answers: { message: '<script>alert("lead")</script> & <img src=x onerror=alert(1)>' },
      files: [{ ...capture.files[0], filename: "<img src=x>.pdf" }],
    });
    expect(html).toContain("&lt;em&gt;Consultation&lt;/em&gt;");
    expect(html).toContain(answer(
      "&lt;b&gt;Requirements&lt;/b&gt;",
      "&lt;script&gt;alert(&quot;lead&quot;)&lt;/script&gt; &amp; &lt;img src=x onerror=alert(1)&gt;",
    ));
    expect(html).toContain("<span>&lt;img src=x&gt;.pdf</span>");
    expect(html).not.toMatch(/<(?:script|img|em|b)\b/);
  });

  it("keeps the heading focusable and the status control accessibly named in the detail header", () => {
    const html = render();
    const header = html.match(new RegExp(`<div class="${styles.detailHeader}">([\\s\\S]*?)</div>`))?.[1];
    expect(header).toBeDefined();
    expect(header).toMatch(/<h3\b[^>]*tabindex="-1"[^>]*>Regional infrastructure support consultation<\/h3>/);
    const statusButton = header?.match(/<button\b[^>]*role="combobox"[^>]*>/)?.[0];
    expect(statusButton).toContain('aria-label="Status"');
  });

  it("retains agent and timestamp metadata and identifies dashboard test leads", () => {
    const html = render();
    expect(html).toContain("Infrastructure support agent · ");
    expect(html).toMatch(/<time dateTime="2026-10-15T10:00:00\+00:00">[^<]+<\/time>/i);
    expect(html).toContain(" · test lead from the dashboard");
  });

  it.each(["widget", "api", "a2a"] as const)("does not label a %s lead as a dashboard test or link its conversation", (source) => {
    const html = render({ source });
    expect(html).toContain("Infrastructure support agent");
    expect(html).not.toContain("test lead from the dashboard");
    expect(html).not.toContain('href="/dashboard/conversations/');
    expect(html).toMatch(/<button\b[^>]*>[\s\S]*?Delete<\/button>/);
  });

  it("retains the attachment download button with its full filename in a wrapping span", () => {
    const html = render();
    const attachment = html.match(new RegExp(`<div class="${styles.actions} ${styles.attachments}">([\\s\\S]*?)</div>`))?.[1];
    expect(attachment).toMatch(/^<button\b[^>]*type="button"/);
    expect(attachment).toContain(`<span>${filename}</span></button>`);
    expect(attachment).toContain('aria-hidden="true"');
    expect(render({ files: [] })).not.toContain(`class="${styles.actions} ${styles.attachments}"`);
  });

  it("retains the dashboard conversation link and delete action", () => {
    const html = render();
    expect(html).toMatch(/<a\b[^>]*href="\/dashboard\/conversations\/conversation-1"[^>]*>[\s\S]*?Conversation<\/a>/);
    expect(html).toMatch(/<button\b[^>]*type="button"[^>]*>[\s\S]*?Delete<\/button>/);
    expect(render({ conversation_id: null })).not.toContain('href="/dashboard/conversations/');
  });
});

describe("CaptureDetail layout safeguards", () => {
  function baseRule(selector: string): string {
    const baseCss = css.split("@media")[0];
    const rule = baseCss.split(`${selector} {`)[1]?.split("}")[0];
    expect(rule, `Missing base rule for ${selector}`).toBeDefined();
    return rule ?? "";
  }

  it.each([".detailHeader", ".answers", ".answer"])("stacks %s in a shrinkable single column at the base viewport", (selector) => {
    const rule = baseRule(selector);
    expect(rule).toMatch(/display:\s*grid\s*;/);
    expect(rule).toMatch(/grid-template-columns:\s*minmax\(\s*0\s*,\s*1fr\s*\)\s*;/);
  });

  it("wraps long labels, multiline answers, and attachment filenames", () => {
    for (const selector of [".answers dt", ".answers dd", ".attachments > button > span"]) {
      expect(baseRule(selector)).toMatch(/overflow-wrap:\s*anywhere\s*;/);
    }
    expect(baseRule(".answers dd")).toMatch(/white-space:\s*pre-wrap\s*;/);
    expect(baseRule(".attachments > button")).toMatch(/white-space:\s*normal\s*;/);
  });
});
