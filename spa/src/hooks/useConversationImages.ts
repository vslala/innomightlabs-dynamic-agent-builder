import { useCallback, useEffect, useState } from "react";
import type { ClipboardEvent } from "react";
import {
  imageFilesFromClipboard,
  imageFilesFromDrop,
  type ImageInputAvailability,
} from "../../packages/image-attachments/src";
import { agentApiService } from "../services/agents/AgentApiService";
import { conversationApiService } from "../services/conversations";
import { useImageAttachments } from "./useImageAttachments";

const isImageFile = (file: File) => file.type.startsWith("image/");

const UNAVAILABLE_FALLBACK = "Images can't be attached to this agent's messages.";

/**
 * Images in one conversation's composer: whether the agent can read them, and paste, drop and the file picker.
 *
 * The API decides availability (account setting, agent type) and sends the limits; nothing is decided here.
 */
export function useConversationImages(conversationId: string | undefined, agentId: string | undefined) {
  const [availability, setAvailability] = useState<ImageInputAvailability | null>(null);
  const [unavailableOpen, setUnavailableOpen] = useState(false);

  useEffect(() => {
    if (!agentId) return;
    let current = true;
    agentApiService
      .getImageInput(agentId)
      .then((result) => current && setAvailability(result))
      // Ila's chats and agents the caller can't chat with have no answer: no images there.
      .catch(() => current && setAvailability(null));
    return () => {
      current = false;
    };
  }, [agentId]);

  const upload = useCallback(
    (file: File) => {
      if (!conversationId) return Promise.reject(new Error("This conversation isn't loaded yet."));
      return conversationApiService.uploadImage(conversationId, file);
    },
    [conversationId],
  );
  const attached = useImageAttachments(upload, availability?.available ? availability.limits : undefined);
  const { addImages } = attached;

  /** Attaches the images among `files`, or explains why it can't; returns the files that aren't images. */
  const takeImages = useCallback(
    (files: File[]): File[] => {
      const images = files.filter(isImageFile);
      if (images.length > 0) {
        if (availability?.available) addImages(images);
        else setUnavailableOpen(true);
      }
      return files.filter((file) => !isImageFile(file));
    },
    [availability, addImages],
  );

  const onPaste = useCallback(
    (event: ClipboardEvent<HTMLTextAreaElement>) => {
      const images = imageFilesFromClipboard(event.clipboardData);
      if (images.length === 0) return;
      event.preventDefault();
      takeImages(images);
    },
    [takeImages],
  );

  /** Files dropped on the composer; returns the ones that aren't images, for the text-file path. */
  const onDrop = useCallback(
    (data: DataTransfer): File[] => {
      const dropped = Array.from(data.files);
      takeImages(imageFilesFromDrop(data));
      return dropped.filter((file) => !isImageFile(file));
    },
    [takeImages],
  );

  return {
    ...attached,
    available: availability?.available ?? false,
    /** What to put in the file picker's `accept`, beside the text types, when images are available. */
    imageTypes: availability?.available ? availability.limits.formats : [],
    unavailableMessage: availability?.message ?? UNAVAILABLE_FALLBACK,
    unavailableOpen,
    setUnavailableOpen,
    hasFailed: attached.images.some((image) => image.status === "failed"),
    takeImages,
    onPaste,
    onDrop,
  };
}
