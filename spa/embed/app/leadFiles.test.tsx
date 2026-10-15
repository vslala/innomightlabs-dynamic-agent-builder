import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WidgetApi, type AgentForm } from "./api";
import { FormCard } from "./components/FormCard";

const CLAIM: AgentForm = {
  form_name: "Damage claim",
  form_inputs: [
    { input_type: "text", name: "name", label: "Name" },
    {
      input_type: "file_upload",
      name: "evidence",
      label: "Photo of the damage",
      validation: { max_items: 2, accept: ["image/png", "application/pdf"] },
    },
  ],
};
const upload = vi.fn();

afterEach(() => vi.unstubAllGlobals());

describe("file fields in forms", () => {
  it("take uploads in the account's lead forms", () => {
    const html = renderToStaticMarkup(
      <FormCard pending={{ form: CLAIM, submitLabel: "Send", leadForm: "claim" }} disabled={false} onSubmit={vi.fn()}
                uploadLeadFile={upload} />
    );

    expect(html).toContain('type="file"');
    expect(html).toContain('accept="image/png,application/pdf"');
    expect(html).toContain("multiple");
  });

  it("are refused in forms the agent made up, which have nothing to check uploads against", () => {
    const html = renderToStaticMarkup(
      <FormCard pending={{ form: CLAIM, submitLabel: "Send" }} disabled={false} onSubmit={vi.fn()} uploadLeadFile={upload} />
    );

    expect(html).not.toContain('type="file"');
    expect(html).toContain("file uploads aren&#x27;t supported in this chat");
  });

  it("upload against the lead form's field", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ file_id: "f1", filename: "dent.png", content_type: "image/png", size_bytes: 3 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      })
    );
    vi.stubGlobal("fetch", fetcher);
    const api = new WidgetApi("pk_test", async () => "token");

    const uploaded = await api.uploadLeadFile("conv 1", "claim", "evidence", new File(["png"], "dent.png", { type: "image/png" }));

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/widget/conversations/conv%201/lead-files");
    const body = init.body as FormData;
    expect([body.get("form"), body.get("input")]).toEqual(["claim", "evidence"]);
    expect(uploaded.file_id).toBe("f1");
  });
});
