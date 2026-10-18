import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Code, Copy, Maximize2 } from "lucide-react";
import { Button } from "./button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "./dialog";
import { renderMermaid } from "./mermaid-runtime";
import styles from "./mermaid-diagram.module.css";

export interface MermaidDiagramProps {
  source: string;
  pending?: boolean;
  className?: string;
  label?: string;
}

function isDarkTheme(): boolean {
  if (typeof document === "undefined") return true;
  const theme = document.documentElement.dataset.theme;
  return theme ? theme !== "light" : !window.matchMedia("(prefers-color-scheme: light)").matches;
}

function DiagramBody({ children }: { children: ReactNode }) {
  const body = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const element = body.current;
    const inner = content.current;
    if (!element || !inner) return;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let previousHeight = inner.getBoundingClientRect().height;
    element.style.height = `${previousHeight}px`;
    let animation: Animation | undefined;
    // Observe the natural content height, not the animated wrapper, so async SVG
    // insertion and rapid toggles can retarget without a resize feedback loop.
    const observer = new ResizeObserver(() => {
      const height = inner.getBoundingClientRect().height;
      if (Math.abs(height - previousHeight) < 1) return;
      const from = animation?.playState === "running" ? element.getBoundingClientRect().height : previousHeight;
      previousHeight = height;
      animation?.cancel();
      element.style.height = `${height}px`;
      if (reducedMotion.matches) return;
      animation = element.animate(
        [{ height: `${from}px` }, { height: `${height}px` }],
        { duration: 220, easing: "ease-out" },
      );
    });
    const stopAnimation = () => { if (reducedMotion.matches) animation?.cancel(); };
    reducedMotion.addEventListener("change", stopAnimation);
    observer.observe(inner);
    return () => {
      observer.disconnect();
      animation?.cancel();
      reducedMotion.removeEventListener("change", stopAnimation);
    };
  }, []);

  return <div ref={body} className={styles.body}><div ref={content} className={styles.bodyContent}>{children}</div></div>;
}

function DiagramImage({ source, dark, label }: { source: string; dark: boolean; label: string }) {
  const host = useRef<HTMLDivElement>(null);
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const [result, setResult] = useState<{ source: string; dark: boolean; failed: boolean }>();
  const current = result?.source === source && result.dark === dark;

  useEffect(() => {
    let active = true;
    let observer: ResizeObserver | undefined;
    const element = host.current;
    // Each attempt, including StrictMode replays and expanded views, needs distinct SVG IDs.
    const svgId = `mermaid-${id}-${crypto.randomUUID()}`;
    void renderMermaid(source, svgId, dark).then((svg) => {
      if (!active || !element) return;
      // Only the official runtime's strict-sanitized SVG crosses this boundary.
      element.innerHTML = svg;
      const image = element.querySelector("svg");
      if (!image) throw new Error("Missing diagram SVG");
      image.setAttribute("role", "img");
      image.setAttribute("aria-label", label);
      const width = image.viewBox.baseVal.width || Number.parseFloat(image.getAttribute("width") || "0");
      const fit = () => {
        if (!width) return;
        const padding = getComputedStyle(element);
        const available = element.clientWidth - Number.parseFloat(padding.paddingLeft) - Number.parseFloat(padding.paddingRight);
        image.style.width = `${Math.max(width * 0.85, Math.min(width, available))}px`;
        image.style.maxWidth = "none";
        image.style.height = "auto";
      };
      fit();
      observer = new ResizeObserver(fit);
      observer.observe(element);
      setResult({ source, dark, failed: false });
    }).catch(() => {
      if (!active) return;
      element?.replaceChildren();
      setResult({ source, dark, failed: true });
    });
    return () => {
      active = false;
      observer?.disconnect();
      element?.replaceChildren();
    };
  }, [source, dark, id, label]);

  return <>
    {!current && <p className={styles.status} role="status">Rendering diagram…</p>}
    {current && result.failed && <>
      <p className={styles.status} role="status">Diagram unavailable. Mermaid source is shown below.</p>
      <pre className={styles.source}><code>{source}</code></pre>
    </>}
    <div ref={host} className={styles.viewport} tabIndex={0} role="region" aria-label={`${label}; scroll to explore`} />
  </>;
}

export function MermaidDiagram({ source, pending = false, className, label = "Mermaid diagram" }: MermaidDiagramProps) {
  const [dark, setDark] = useState(isDarkTheme);
  const [showSource, setShowSource] = useState(false);
  const [copyResult, setCopyResult] = useState<{ source: string; message: string }>();
  const copyStatus = copyResult?.source === source ? copyResult.message : "";

  useEffect(() => {
    const sync = () => setDark(isDarkTheme());
    const observer = new MutationObserver(sync);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    const media = window.matchMedia("(prefers-color-scheme: light)");
    media.addEventListener("change", sync);
    return () => { observer.disconnect(); media.removeEventListener("change", sync); };
  }, []);

  async function copySource() {
    try {
      await navigator.clipboard.writeText(source);
      setCopyResult({ source, message: "Source copied" });
    } catch {
      setShowSource(true);
      setCopyResult({ source, message: "Select and copy the source below" });
    }
  }

  return <section className={`${styles.card} ${className || ""}`} aria-label={label}>
    <div className={styles.toolbar}>
      <span className={styles.title}>Mermaid</span>
      <div className={styles.actions}>
        <Button type="button" variant="ghost" size="icon" aria-label="Toggle Mermaid source" aria-pressed={showSource} onClick={() => setShowSource(!showSource)}><Code aria-hidden="true" /></Button>
        <Button type="button" variant="ghost" size="icon" aria-label="Copy Mermaid source" onClick={() => void copySource()}><Copy aria-hidden="true" /></Button>
        <Dialog>
          <DialogTrigger asChild><Button type="button" variant="ghost" size="icon" aria-label="Expand diagram" disabled={pending}><Maximize2 aria-hidden="true" /></Button></DialogTrigger>
          <DialogContent className={styles.expanded}>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>Scroll to explore the full diagram. Press Escape to close.</DialogDescription>
            <DiagramImage source={source} dark={dark} label={label} />
          </DialogContent>
        </Dialog>
      </div>
    </div>
    <DiagramBody>
    {copyStatus && <p className={styles.status} role="status">{copyStatus}</p>}
    {pending && <p className={styles.status} role="status">Diagram will render when the response is complete.</p>}
    {(showSource || pending) && <pre className={styles.source} tabIndex={0} role="region" aria-label="Mermaid source"><code>{source}</code></pre>}
    {!pending && <div hidden={showSource}>
      <DiagramImage source={source} dark={dark} label={label} />
    </div>}
    </DiagramBody>
  </section>;
}
