import { Loader2 } from "lucide-react";
import styles from "./ConversationParts.module.css";

export interface StreamingImage {
  prompt: string;
  /** The latest partial picture, or null before the first one arrives. */
  dataUrl: string | null;
  status: string;
}

/** The image being painted: its partial previews as they stream in, with the status over them. */
export function StreamingImagePreview({ image }: { image: StreamingImage }) {
  return (
    <div className={styles.panel}>
      <div className={styles.imageTitle}>Generating image: {image.prompt}</div>
      <div className={styles.imageStage}>
        {image.dataUrl ? (
          <>
            <img src={image.dataUrl} alt={image.prompt} className={styles.imagePreview} />
            <div className={styles.imageStatus} role="status">{image.status}</div>
          </>
        ) : (
          <div className={styles.imageLoading} role="status">
            <Loader2 className={styles.spinner} />
            <span>{image.status}</span>
          </div>
        )}
      </div>
    </div>
  );
}
