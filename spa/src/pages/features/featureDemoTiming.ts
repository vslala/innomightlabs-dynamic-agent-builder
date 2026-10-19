import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from "react";

const motionQuery = '(prefers-reduced-motion: reduce)';
const subscribeMotion = (notify: () => void) => {
  const query = window.matchMedia(motionQuery);
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
};
export function useReducedMotion() {
  return useSyncExternalStore(subscribeMotion, () => window.matchMedia(motionQuery).matches, () => false);
}

/** A bounded, visibility-started demo clock. Replays replace, rather than overlap, the old timeline. */
export function useDemoClock(duration: number, loop = false) {
  const ref = useRef<HTMLDivElement>(null);
  const attach = useCallback((element: HTMLDivElement | null) => { ref.current = element; }, []);
  const reduced = useReducedMotion();
  const [revision, setRevision] = useState(0);
  const [frame, setFrame] = useState({ revision: 0, elapsed: 0 });
  useEffect(() => {
    if (reduced) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    const start = () => {
      if (timer !== undefined) return;
      const began = performance.now();
      timer = setInterval(() => {
        const elapsed = performance.now() - began;
        setFrame({ revision, elapsed: loop ? elapsed % duration : Math.min(duration, elapsed) });
        if (!loop && elapsed >= duration) clearInterval(timer);
      }, 40);
    };
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) { start(); observer.disconnect(); }
    }, { threshold: 0.25 });
    if (ref.current) observer.observe(ref.current);
    return () => { observer.disconnect(); clearInterval(timer); };
  }, [duration, loop, reduced, revision]);
  return { attach, reduced, elapsed: reduced ? duration : frame.revision === revision ? frame.elapsed : 0, replay: () => setRevision(value => value + 1) };
}

export type ChatLine = readonly ['u' | 'a', string];
export function chatDuration(lines: readonly ChatLine[], speed = 18, pause = 0, exchangePause = 0) {
  return lines.reduce((total, [who, text]) => total + (who === 'u' ? text.length * speed : 900) + pause + (who === 'a' ? exchangePause : 0), 0);
}
export const nodeColor = (color: string) => ({ "--c": `var(--${color})` }) as CSSProperties;
