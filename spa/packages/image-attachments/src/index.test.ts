import { describe, expect, it } from "vitest";
import {
  imageErrorMessage,
  imageFilesFromClipboard,
  imageFilesFromDrop,
  isFileDrag,
  validateImageFiles,
  type ImageInputLimits,
} from "./index";

const LIMITS: ImageInputLimits = {
  max_bytes: 5 * 1024 * 1024,
  max_images_per_message: 2,
  max_edge_px: 2000,
  max_pixels: 40_000_000,
  formats: ["image/png", "image/jpeg", "image/webp", "image/gif"],
};

const file = (name: string, type: string, size = 100) => new File([new Uint8Array(size)], name, { type });

/** The slice of DataTransfer these functions read. */
function transfer(init: { text?: string; files?: File[]; items?: File[]; types?: string[] }): DataTransfer {
  const files = init.files ?? [];
  return {
    getData: (kind: string) => (kind === "text/plain" ? (init.text ?? "") : ""),
    files: Object.assign([...files], { item: (i: number) => files[i] }),
    items: (init.items ?? []).map((f) => ({ kind: "file", getAsFile: () => f })),
    types: init.types ?? [],
  } as unknown as DataTransfer;
}

describe("imageFilesFromClipboard", () => {
  it("takes a pasted screenshot", () => {
    const shot = file("image.png", "image/png");

    expect(imageFilesFromClipboard(transfer({ files: [shot] }))).toEqual([shot]);
  });

  it("falls back to clipboard items when the file list is empty", () => {
    const shot = file("image.png", "image/png");

    expect(imageFilesFromClipboard(transfer({ items: [shot] }))).toEqual([shot]);
  });

  it("leaves a paste that carries text as a text paste", () => {
    const rendered = file("image.png", "image/png");

    expect(imageFilesFromClipboard(transfer({ text: "a1, b2", files: [rendered] }))).toEqual([]);
  });

  it("ignores files that are not images", () => {
    expect(imageFilesFromClipboard(transfer({ files: [file("notes.txt", "text/plain")] }))).toEqual([]);
  });

  it("handles an empty clipboard", () => {
    expect(imageFilesFromClipboard(null)).toEqual([]);
  });
});

describe("drag and drop", () => {
  it("takes only the images from a drop", () => {
    const photo = file("a.jpg", "image/jpeg");

    expect(imageFilesFromDrop(transfer({ files: [photo, file("b.pdf", "application/pdf")] }))).toEqual([photo]);
  });

  it("recognises a drag that carries files", () => {
    expect(isFileDrag(transfer({ types: ["Files"] }))).toBe(true);
    expect(isFileDrag(transfer({ types: ["text/plain"] }))).toBe(false);
    expect(isFileDrag(null)).toBe(false);
  });
});

describe("validateImageFiles", () => {
  it("accepts images within the limits", () => {
    const photo = file("a.png", "image/png");

    expect(validateImageFiles([photo], LIMITS, 0)).toEqual({ accepted: [photo], error: null });
  });

  it("refuses a format the providers don't read", () => {
    const result = validateImageFiles([file("a.bmp", "image/bmp")], LIMITS, 0);

    expect(result.accepted).toEqual([]);
    expect(result.error).toBe("Only PNG, JPEG, WebP and GIF images are supported.");
  });

  it("refuses an image over the size limit, in whole megabytes", () => {
    const result = validateImageFiles([file("big.png", "image/png", LIMITS.max_bytes + 1)], LIMITS, 0);

    expect(result.error).toBe("Images must be 5MB or smaller.");
  });

  it("counts images already on the message toward the limit", () => {
    const [first, second] = [file("1.png", "image/png"), file("2.png", "image/png")];

    const result = validateImageFiles([first, second], LIMITS, 1);

    expect(result.accepted).toEqual([first]);
    expect(result.error).toBe("Up to 2 images per message.");
  });

  it("keeps the good files and reports the first problem", () => {
    const good = file("a.png", "image/png");

    const result = validateImageFiles([file("x.bmp", "image/bmp"), good], LIMITS, 0);

    expect(result.accepted).toEqual([good]);
    expect(result.error).toBe("Only PNG, JPEG, WebP and GIF images are supported.");
  });
});

describe("imageErrorMessage", () => {
  it("uses the API's message", () => {
    expect(imageErrorMessage({ code: "image_input_disabled", message: "Image input is turned off." })).toBe(
      "Image input is turned off.",
    );
  });

  it("falls back for anything else", () => {
    expect(imageErrorMessage("Internal error")).toBe("The image could not be uploaded. Please try again.");
    expect(imageErrorMessage(undefined, "Oops")).toBe("Oops");
  });
});
