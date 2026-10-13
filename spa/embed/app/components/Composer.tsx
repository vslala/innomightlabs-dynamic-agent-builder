import { forwardRef, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent } from "react";
import { ArrowUp, ImagePlus, Loader2, RotateCw, X } from "lucide-react";

import {
  imageFilesFromClipboard,
  imageFilesFromDrop,
  isFileDrag,
  type ImageInputAvailability,
  type UploadedImage,
} from "../../../packages/image-attachments/src";
import { useImageAttachments } from "../../../src/hooks/useImageAttachments";
import type { SentImage } from "../useChat";

interface ComposerProps {
  placeholder: string;
  disabled: boolean;
  /** From the shell: whether visitors may attach images here. Without it the composer is text only. */
  imageInput?: ImageInputAvailability;
  uploadImage: (file: File) => Promise<UploadedImage>;
  onSend: (content: string, images: SentImage[]) => void;
}

const MAX_ROWS = 6;

export const Composer = forwardRef<HTMLTextAreaElement, ComposerProps>(function Composer(
  { placeholder, disabled, imageInput, uploadImage, onSend },
  ref
) {
  const [value, setValue] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const imagesAllowed = imageInput?.available === true;
  const attached = useImageAttachments(uploadImage, imagesAllowed ? imageInput.limits : undefined);
  const rows = Math.min(MAX_ROWS, Math.max(1, value.split("\n").length));

  const sendable = attached.images.filter((image) => image.imageId);
  const failed = attached.images.find((image) => image.status === "failed");
  const hasContent = value.trim() !== "" || sendable.length > 0;
  const canSend = hasContent && !disabled && !attached.isUploading && !failed;
  const message = attached.error ?? failed?.error ?? null;

  const send = () => {
    if (!canSend) return;
    onSend(
      value.trim(),
      sendable.map((image) => ({ imageId: image.imageId as string, name: image.file.name, src: image.previewUrl }))
    );
    setValue("");
    attached.clearImages();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send();
    }
  };

  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    if (!imagesAllowed) return;
    const files = imageFilesFromClipboard(event.clipboardData);
    if (files.length === 0) return;
    event.preventDefault();
    attached.addImages(files);
  };

  const dropEnabled = imagesAllowed && !disabled;
  const onDragOver = (event: DragEvent<HTMLDivElement>) => {
    if (!dropEnabled || !isFileDrag(event.dataTransfer)) return;
    event.preventDefault();
    setDragging(true);
  };
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    if (!dropEnabled) return;
    event.preventDefault();
    setDragging(false);
    attached.addImages(imageFilesFromDrop(event.dataTransfer));
  };

  return (
    <>
      {attached.images.length > 0 && (
        <ul className="ie-composer-images" aria-label="Attached images">
          {attached.images.map((image) => (
            <li key={image.localId} className="ie-composer-image" data-status={image.status}>
              <img src={image.previewUrl} alt={image.file.name} />
              {image.status === "uploading" && (
                <span className="ie-composer-image-state" role="status" aria-label={`Uploading ${image.file.name}`}>
                  <Loader2 className="ie-spin" aria-hidden="true" />
                </span>
              )}
              {image.status === "failed" && (
                <button
                  type="button"
                  className="ie-composer-image-state"
                  aria-label={`Retry uploading ${image.file.name}`}
                  onClick={() => attached.retryImage(image.localId)}
                >
                  <RotateCw aria-hidden="true" />
                </button>
              )}
              <button
                type="button"
                className="ie-composer-image-remove"
                aria-label={`Remove ${image.file.name}`}
                onClick={() => attached.removeImage(image.localId)}
              >
                <X aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      {message && (
        <p className="ie-composer-error" role="alert">
          {message}
        </p>
      )}
      <div className="ie-composer" data-dragging={dragging || undefined} onDragOver={onDragOver} onDragLeave={() => setDragging(false)} onDrop={onDrop}>
        {imagesAllowed && (
          <>
            <input
              ref={fileInput}
              type="file"
              hidden
              multiple
              accept={imageInput.limits.formats.join(",")}
              onChange={(event) => {
                attached.addImages(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <button type="button" className="ie-attach" aria-label="Attach an image" disabled={disabled} onClick={() => fileInput.current?.click()}>
              <ImagePlus aria-hidden="true" />
            </button>
          </>
        )}
        <textarea
          ref={ref}
          className="ie-composer-input"
          rows={rows}
          value={value}
          placeholder={placeholder}
          aria-label="Message"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
        <button type="button" className="ie-send" aria-label="Send message" disabled={!canSend} onClick={send}>
          <ArrowUp aria-hidden="true" />
        </button>
      </div>
    </>
  );
});
