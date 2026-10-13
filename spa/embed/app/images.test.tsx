import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ImageInputAvailability } from "../../packages/image-attachments/src";
import { WidgetApi } from "./api";
import { Composer } from "./components/Composer";

const LIMITS = {
  max_bytes: 5 * 1024 * 1024,
  max_images_per_message: 4,
  max_edge_px: 2000,
  max_pixels: 40_000_000,
  formats: ["image/png", "image/jpeg", "image/webp", "image/gif"],
};
const AVAILABLE: ImageInputAvailability = { available: true, reason: null, message: null, limits: LIMITS };
const DISABLED: ImageInputAvailability = {
  available: false,
  reason: "image_input_disabled",
  message: "Image input is turned off for this account.",
  limits: LIMITS,
};

function respond(body: unknown, status = 200, type = "application/json") {
  const payload = type === "application/json" ? JSON.stringify(body) : (body as BodyInit);
  return new Response(payload, { status, headers: { "Content-Type": type } });
}

afterEach(() => vi.unstubAllGlobals());

describe("composer", () => {
  const props = { placeholder: "Write…", disabled: false, uploadImage: vi.fn(), onSend: vi.fn() };

  it("offers attaching images when the account allows them", () => {
    const html = renderToStaticMarkup(<Composer {...props} imageInput={AVAILABLE} />);

    expect(html).toContain('aria-label="Attach an image"');
    expect(html).toContain('accept="image/png,image/jpeg,image/webp,image/gif"');
  });

  it("stays text only when images are off, or when the shell says nothing", () => {
    expect(renderToStaticMarkup(<Composer {...props} imageInput={DISABLED} />)).not.toContain("Attach an image");
    expect(renderToStaticMarkup(<Composer {...props} />)).not.toContain("Attach an image");
  });

  it("starts with nothing to send", () => {
    const html = renderToStaticMarkup(<Composer {...props} imageInput={AVAILABLE} />);

    expect(html).toMatch(/<button[^>]*aria-label="Send message"[^>]*disabled=""/);
  });
});

describe("widget API images", () => {
  it("uploads a file as multipart, with the visitor's headers and no JSON content type", async () => {
    const fetcher = vi.fn().mockResolvedValue(respond({ image_id: "img-1", filename: "shot.png" }, 201));
    vi.stubGlobal("fetch", fetcher);
    const api = new WidgetApi("pk_test", async () => "token");

    await api.uploadImage("conv 1", new File(["x"], "shot.png", { type: "image/png" }));

    const [url, init] = fetcher.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/widget/conversations/conv%201/images");
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.headers).toEqual({ "X-API-Key": "pk_test", Authorization: "Bearer token" });
  });

  it("sends the image ids with the message", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetcher);
    const api = new WidgetApi("pk", async () => "token");

    await api.sendMessage("conv-1", "what is this?", ["img-1", "img-2"]).next().catch(() => undefined);

    expect(JSON.parse((fetcher.mock.calls[0][1] as RequestInit).body as string)).toEqual({
      content: "what is this?",
      image_ids: ["img-1", "img-2"],
    });
  });

  it("fetches a saved image through the API path with the visitor's headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(respond("bytes", 200, "image/png"));
    vi.stubGlobal("fetch", fetcher);
    const createObjectURL = vi.fn().mockReturnValue("blob:image");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL }));
    const api = new WidgetApi("pk", async () => "token");

    const src = await api.fetchImage("https://api.example.com/widget/conversations/c1/images/i1");

    expect(src).toBe("blob:image");
    expect(fetcher.mock.calls[0][0]).toBe("/widget/conversations/c1/images/i1");
    expect((fetcher.mock.calls[0][1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer token" });
  });

  it("shows the API's own words when it refuses an image", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(
      { detail: { code: "image_input_disabled", message: "Image input is turned off for this account." } }, 403,
    )));
    const api = new WidgetApi("pk", async () => "token");

    await expect(api.uploadImage("c", new File(["x"], "a.png"))).rejects.toThrow(
      "Image input is turned off for this account.",
    );
  });

  it("explains an upload limit without exposing the code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(
      { detail: { code: "image_upload_limited", message: "Too many images. Try again in a moment." } }, 429,
    )));
    const api = new WidgetApi("pk", async () => "token");

    await expect(api.uploadImage("c", new File(["x"], "a.png"))).rejects.toThrow("Too many images. Try again in a moment.");
  });

  it("keeps the guest message limit's wording for chat messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond({ detail: "guest_message_limited" }, 429)));
    const api = new WidgetApi("pk", async () => "token");

    await expect(api.createConversation("Hi")).rejects.toThrow("continue with Google");
  });
});
