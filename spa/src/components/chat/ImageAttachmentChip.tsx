import { AlertCircle, Loader2, RotateCw, X } from "lucide-react";
import { Button } from "../ui/button";
import type { ComposerImage } from "../../hooks/useImageAttachments";
import styles from "./ImageAttachmentChip.module.css";

interface ImageAttachmentChipProps {
  image: ComposerImage;
  onRemove: () => void;
  onRetry: () => void;
}

/** An image waiting to be sent: its own thumbnail, its upload state, and a way to remove or retry it. */
export function ImageAttachmentChip({ image, onRemove, onRetry }: ImageAttachmentChipProps) {
  return (
    <div className={styles.chip} data-status={image.status} title={image.error ?? image.file.name}>
      <img className={styles.thumbnail} src={image.previewUrl} alt={image.file.name} />
      {image.status === "uploading" && (
        <span className={styles.overlay} role="status" aria-label={`Uploading ${image.file.name}`}>
          <Loader2 className={styles.spinner} />
        </span>
      )}
      {image.status === "failed" && (
        <span className={styles.overlay}>
          <AlertCircle className={styles.failedIcon} aria-hidden="true" />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={styles.retry}
            onClick={onRetry}
            aria-label={`Retry uploading ${image.file.name}`}
          >
            <RotateCw size={14} />
          </Button>
        </span>
      )}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={styles.remove}
        onClick={onRemove}
        aria-label={`Remove ${image.file.name}`}
      >
        <X size={12} />
      </Button>
    </div>
  );
}
