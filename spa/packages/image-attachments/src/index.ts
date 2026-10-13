/**
 * Getting images out of paste and drop events and checking them against the server's limits. Shared by the
 * dashboard composer and the embed widget, so both accept exactly what the API accepts. Pure functions: no React,
 * no HTTP.
 */

export type ImageInputUnavailableReason =
  | "image_input_disabled"
  | "image_input_not_configured"
  | "image_input_agent_unsupported";

/** What an image may be; the API sends it with `ImageInputAvailability`, so the browser never keeps its own copy. */
export interface ImageInputLimits {
  max_bytes: number;
  max_images_per_message: number;
  max_edge_px: number;
  max_pixels: number;
  formats: string[];
}

export interface ImageInputAvailability {
  available: boolean;
  reason: ImageInputUnavailableReason | null;
  message: string | null;
  limits: ImageInputLimits;
}

/** An image the API stored and a message can carry by id. */
export interface UploadedImage {
  image_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  url: string;
}

const MEGABYTE = 1024 * 1024;

/**
 * Images on the clipboard. A paste that also carries text (a spreadsheet cell, a styled paragraph) stays a text
 * paste: those copies include a rendered picture too, and attaching it would break ordinary pasting.
 */
export function imageFilesFromClipboard(data: DataTransfer | null): File[] {
  if (!data || data.getData("text/plain")) return [];
  const files = data.files.length > 0 ? Array.from(data.files) : filesOfItems(data.items);
  return files.filter(isImage);
}

/** Images dropped onto the composer. */
export function imageFilesFromDrop(data: DataTransfer | null): File[] {
  if (!data) return [];
  return Array.from(data.files).filter(isImage);
}

/** Whether a drag in progress carries files, so the composer can show where to drop them. */
export function isFileDrag(data: DataTransfer | null): boolean {
  return Boolean(data && Array.from(data.types).includes("Files"));
}

export interface ImageValidation {
  accepted: File[];
  /** The first thing wrong, in words fit for the person attaching; null when every file was accepted. */
  error: string | null;
}

/** The files that fit the limits, and why the others didn't. `alreadyAttached` counts what the message holds. */
export function validateImageFiles(files: File[], limits: ImageInputLimits, alreadyAttached: number): ImageValidation {
  const accepted: File[] = [];
  let error: string | null = null;
  for (const file of files) {
    if (!limits.formats.includes(file.type)) {
      error ??= "Only PNG, JPEG, WebP and GIF images are supported.";
    } else if (file.size > limits.max_bytes) {
      error ??= `Images must be ${Math.floor(limits.max_bytes / MEGABYTE)}MB or smaller.`;
    } else if (alreadyAttached + accepted.length >= limits.max_images_per_message) {
      error ??= `Up to ${limits.max_images_per_message} images per message.`;
    } else {
      accepted.push(file);
    }
  }
  return { accepted, error };
}

/** The API's own message for a refused image (`{detail: {code, message}}`), or the fallback. */
export function imageErrorMessage(detail: unknown, fallback = "The image could not be uploaded. Please try again."): string {
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") {
    return detail.message;
  }
  return fallback;
}

function isImage(file: File): boolean {
  return file.type.startsWith("image/");
}

function filesOfItems(items: DataTransferItemList | undefined): File[] {
  if (!items) return [];
  return Array.from(items)
    .filter((item) => item.kind === "file")
    .map((item) => item.getAsFile())
    .filter((file): file is File => file !== null);
}
