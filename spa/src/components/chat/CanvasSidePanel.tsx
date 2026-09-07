import { ExternalLink, X } from "lucide-react";

import { useArtifactHtml } from "../../hooks/useArtifactHtml";
import type { MessageCanvasArtifact } from "../../types/message";
import { CanvasPlaceholder } from "./CanvasPlaceholder";
import styles from "./CanvasSidePanel.module.css";

interface CanvasSidePanelProps {
  canvas: MessageCanvasArtifact;
  onClose: () => void;
}

export function CanvasSidePanel({ canvas, onClose }: CanvasSidePanelProps) {
  const state = useArtifactHtml(canvas.content_url, true);

  return (
    <aside className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <h2 className={styles.panelTitle}>{canvas.title}</h2>
          {canvas.caption && <p className={styles.panelCaption}>{canvas.caption}</p>}
        </div>
        <div className={styles.panelActions}>
          {canvas.open_url && (
            <a href={canvas.open_url} target="_blank" rel="noreferrer" className={styles.openLink}>
              <ExternalLink style={{ height: "0.875rem", width: "0.875rem" }} />
              Open full page
            </a>
          )}
          <button type="button" onClick={onClose} aria-label="Close canvas panel" className={styles.closeButton}>
            <X style={{ height: "1rem", width: "1rem" }} />
          </button>
        </div>
      </div>
      <div className={styles.panelBody}>
        {state.status === "loading" && <CanvasPlaceholder mode="loading" />}
        {state.status === "failed" && <CanvasPlaceholder mode="failed" />}
        {state.status === "loaded" && (
          <iframe
            srcDoc={state.html}
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            title={canvas.title}
            className={styles.panelIframe}
          />
        )}
      </div>
    </aside>
  );
}
