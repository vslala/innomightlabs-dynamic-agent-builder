import { useEffect, useRef, useState } from "react";
import { Maximize2 } from "lucide-react";

import { useArtifactHtml } from "../../hooks/useArtifactHtml";
import type { MessageCanvasArtifact } from "../../types/message";
import { CanvasPlaceholder } from "./CanvasPlaceholder";
import styles from "./InlineCanvasCard.module.css";

interface InlineCanvasCardProps {
  canvas: MessageCanvasArtifact;
  onExpand: (canvas: MessageCanvasArtifact) => void;
}

export function InlineCanvasCard({ canvas, onExpand }: InlineCanvasCardProps) {
  const [visible, setVisible] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const state = useArtifactHtml(canvas.content_url, visible);

  return (
    <div ref={containerRef} className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.cardTitle}>{canvas.title}</span>
        <button
          type="button"
          className={styles.expandButton}
          onClick={() => onExpand(canvas)}
          aria-label="Expand canvas"
          title="Expand canvas"
        >
          <Maximize2 style={{ height: "0.875rem", width: "0.875rem" }} />
        </button>
      </div>
      <div className={styles.previewFrame}>
        {state.status === "loading" && <CanvasPlaceholder mode="loading" />}
        {state.status === "failed" && <CanvasPlaceholder mode="failed" />}
        {state.status === "loaded" && (
          <iframe
            srcDoc={state.html}
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            title={canvas.title}
            className={styles.previewIframe}
          />
        )}
      </div>
      {canvas.caption && <p className={styles.caption}>{canvas.caption}</p>}
    </div>
  );
}
