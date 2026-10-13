import { useCallback, useEffect, useRef, useState } from "react";
import {
  validateImageFiles,
  type ImageInputLimits,
  type UploadedImage,
} from "../../packages/image-attachments/src";

/** One image the person attached: shown at once from the file itself, uploaded in the background. */
export interface ComposerImage {
  localId: string;
  file: File;
  previewUrl: string;
  status: "uploading" | "ready" | "failed";
  /** What to send with the message once `status` is ready. */
  imageId?: string;
  error?: string;
}

interface UseImageAttachmentsReturn {
  images: ComposerImage[];
  error: string | null;
  addImages: (files: File[]) => void;
  retryImage: (localId: string) => void;
  removeImage: (localId: string) => void;
  /** Empties the composer after a send; the previews stay valid for the sent message, until the page unmounts. */
  clearImages: () => void;
  /** True while any image is still uploading: sending then would leave it behind. */
  isUploading: boolean;
  /** The ids to send, in the order attached. Failed images are not included. */
  readyImageIds: string[];
}

/**
 * Images attached to the chat composer: paste, pick and drop all end up in `addImages`.
 *
 * Each image uploads as soon as it is added, so the message goes out without waiting on the network. Removing an
 * image just forgets it; the server deletes an upload nobody sent.
 */
export function useImageAttachments(
  upload: (file: File) => Promise<UploadedImage>,
  limits: ImageInputLimits | undefined,
): UseImageAttachmentsReturn {
  const [images, setImages] = useState<ComposerImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const previewUrls = useRef(new Set<string>());

  const patch = useCallback((localId: string, change: Partial<ComposerImage>) => {
    setImages((current) => current.map((image) => (image.localId === localId ? { ...image, ...change } : image)));
  }, []);

  const send = useCallback(
    async (localId: string, file: File) => {
      try {
        const uploaded = await upload(file);
        patch(localId, { status: "ready", imageId: uploaded.image_id, error: undefined });
      } catch (err) {
        patch(localId, { status: "failed", error: err instanceof Error ? err.message : "Upload failed." });
      }
    },
    [upload, patch],
  );

  const addImages = useCallback(
    (files: File[]) => {
      if (!limits || files.length === 0) return;
      const { accepted, error: refusal } = validateImageFiles(files, limits, images.length);
      setError(refusal);
      const added = accepted.map<ComposerImage>((file) => {
        const previewUrl = URL.createObjectURL(file);
        previewUrls.current.add(previewUrl);
        return { localId: crypto.randomUUID(), file, previewUrl, status: "uploading" };
      });
      setImages((current) => [...current, ...added]);
      added.forEach((image) => void send(image.localId, image.file));
    },
    [limits, images.length, send],
  );

  const retryImage = useCallback(
    (localId: string) => {
      const image = images.find((candidate) => candidate.localId === localId);
      if (!image) return;
      patch(localId, { status: "uploading", error: undefined });
      void send(localId, image.file);
    },
    [images, patch, send],
  );

  const forget = useCallback((removed: ComposerImage[]) => {
    removed.forEach((image) => {
      URL.revokeObjectURL(image.previewUrl);
      previewUrls.current.delete(image.previewUrl);
    });
  }, []);

  const removeImage = useCallback(
    (localId: string) => {
      setError(null);
      setImages((current) => {
        forget(current.filter((image) => image.localId === localId));
        return current.filter((image) => image.localId !== localId);
      });
    },
    [forget],
  );

  /** Empty the composer after a send. The previews live on, for the message that now shows them. */
  const clearImages = useCallback(() => {
    setError(null);
    setImages([]);
  }, []);

  useEffect(() => {
    const urls = previewUrls.current;
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  return {
    images,
    error,
    addImages,
    retryImage,
    removeImage,
    clearImages,
    isUploading: images.some((image) => image.status === "uploading"),
    readyImageIds: images.flatMap((image) => (image.imageId ? [image.imageId] : [])),
  };
}
