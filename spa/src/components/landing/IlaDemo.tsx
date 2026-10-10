import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { BookOpen, Bot, Boxes, Check, Link2, Mail, MessageCircle, Puzzle, Sparkles, type LucideIcon } from "lucide-react";
import { SCENARIOS, TYPE_MS, beatsFor, finalFrame, frameAt, type StepKind } from "./ilaScenes";
import styles from "./IlaDemo.module.css";

const STEP_ICONS: Record<StepKind, LucideIcon> = {
  knowledge: BookOpen,
  agent: Bot,
  skill: Puzzle,
  widget: MessageCircle,
};

/** How long the request bubble takes to blink in before its text starts typing (matches `blinkIn` in the CSS). */
const REQUEST_BLINK_MS = 700;

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const media = window.matchMedia(reducedMotionQuery);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(reducedMotionQuery).matches,
    () => false,
  );
}

/**
 * Types its text out while active, after `delay` ms; shows all of it otherwise. Remount it (a new key) to type again.
 * The full text is laid out invisibly underneath, so the bubble holding it has its final size from the start
 * instead of growing as the letters arrive.
 */
function Typed({ text, active, delay = 0 }: { text: string; active: boolean; delay?: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!active) return;
    let interval = 0;
    const start = window.setTimeout(() => {
      interval = window.setInterval(() => setShown((n) => Math.min(n + 1, text.length)), TYPE_MS);
    }, delay);
    return () => {
      window.clearTimeout(start);
      window.clearInterval(interval);
    };
  }, [active, text, delay]);
  return (
    <span className={styles.typed}>
      <span className={styles.ghost}>{text}</span>
      <span>
        {active ? text.slice(0, shown) : text}
        {active && <span className={styles.caret} />}
      </span>
    </span>
  );
}

function IlaMark({ small = false }: { small?: boolean }) {
  return (
    <span className={small ? `${styles.mark} ${styles.markSmall}` : styles.mark}>
      <Sparkles aria-hidden="true" />
    </span>
  );
}

/**
 * The home page's scene of Ila at work. It plays only while on screen; with reduced motion it shows the finished
 * picture of the first scenario instead.
 */
export function IlaDemo() {
  const reducedMotion = usePrefersReducedMotion();
  const [onScreen, setOnScreen] = useState(true);
  const [at, setAt] = useState({ scene: 0, beat: 0 });
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = root.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting), { threshold: 0.2 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const scenario = SCENARIOS[at.scene];
  const beats = beatsFor(scenario);
  const playing = onScreen && !reducedMotion;

  useEffect(() => {
    if (!playing) return;
    const id = window.setTimeout(() => {
      setAt(({ scene, beat }) =>
        beat + 1 < beats.length ? { scene, beat: beat + 1 } : { scene: (scene + 1) % SCENARIOS.length, beat: 0 },
      );
    }, beats[at.beat].ms);
    return () => window.clearTimeout(id);
  }, [playing, at, beats]);

  const shown = reducedMotion ? SCENARIOS[0] : scenario;
  const frame = reducedMotion ? finalFrame(shown) : frameAt(shown, beats[at.beat].phase);
  const ProofIcon = shown.proofKind === "email" ? Mail : Link2;

  return (
    <figure ref={root} className={styles.demo}>
      <figcaption className={styles.caption}>
        Ila at work: someone asks for a website assistant, Ila shows a plan, builds it as a kit after it is approved,
        and the new chat widget answers a visitor's question on the website.
      </figcaption>
      <div key={reducedMotion ? "still" : at.scene} className={styles.stage} data-view={frame.site ? "site" : "studio"} aria-hidden="true">
        <div className={`${styles.window} ${styles.studio}`}>
          <div className={styles.bar}>
            <span className={styles.dots}><i /><i /><i /></span>
            <span className={styles.barTitle}>Build with Ila</span>
          </div>
          <div className={styles.chat}>
            <p className={styles.request}>
              <Typed text={shown.request} active={frame.requestTyping} delay={REQUEST_BLINK_MS} />
            </p>
            {frame.thinking && (
              <div className={styles.ila}>
                <IlaMark />
                <span className={styles.thinking}><i /><i /><i /></span>
              </div>
            )}
            {frame.planShown > 0 && (
              <div className={styles.ila}>
                <IlaMark />
                <div className={styles.ilaBody}>
                  <p className={styles.reply}>{shown.reply}</p>
                  <ol className={styles.plan}>
                    {shown.plan.slice(0, frame.planShown).map((step, index) => {
                      const Icon = STEP_ICONS[step.kind];
                      const built = index < frame.built;
                      return (
                        <li key={`${step.kind}-${step.detail}`} className={built ? `${styles.step} ${styles.built}` : styles.step}>
                          <span className={styles.stepIcon}><Icon aria-hidden="true" /></span>
                          <span className={styles.stepText}>
                            <span className={styles.stepLabel}>{step.label}</span>
                            <span className={styles.stepDetail}>{step.detail}</span>
                          </span>
                          <span className={styles.tick}><Check aria-hidden="true" /></span>
                        </li>
                      );
                    })}
                  </ol>
                  {frame.planShown === shown.plan.length && (
                    <span className={frame.approved ? `${styles.approve} ${styles.approved}` : styles.approve}>
                      {frame.approved ? (frame.kit ? "Built" : "Approved, building…") : "Approve plan"}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        <div className={`${styles.window} ${styles.site}`}>
          <div className={styles.bar}>
            <span className={styles.dots}><i /><i /><i /></span>
            <span className={styles.url}>{shown.site.url}</span>
          </div>
          <div className={styles.page}>
            <div className={styles.siteNav}>
              <strong>{shown.site.name}</strong>
              <span /><span /><span />
            </div>
            <p className={styles.siteTagline}>{shown.site.tagline}</p>
            <span className={styles.line} />
            <span className={`${styles.line} ${styles.lineShort}`} />
            <div className={styles.siteCards}><span /><span /><span /></div>
          </div>
          <div className={styles.widget}>
            <div className={styles.widgetHead}>
              <IlaMark small />
              <span>{shown.site.name} assistant</span>
              <span className={styles.online} />
            </div>
            <div className={styles.widgetBody}>
              {frame.visitorSent && <p className={styles.visitor}>{shown.visitor}</p>}
              {frame.answer && (
                <p className={styles.answer}>
                  <Typed text={shown.answer} active={!frame.proof} />
                </p>
              )}
              {frame.proof && (
                <span className={styles.proof}><ProofIcon aria-hidden="true" /> {shown.proof}</span>
              )}
            </div>
            <div className={styles.widgetInput}>
              {frame.visitorTyping ? <Typed text={shown.visitor} active /> : <span className={styles.placeholder}>Ask a question…</span>}
            </div>
          </div>
        </div>

        {frame.kit && (
          <div className={styles.kit}>
            <span className={styles.kitIcon}><Boxes aria-hidden="true" /></span>
            <span className={styles.kitText}>
              <span className={styles.kitName}>Kit · {shown.kit}</span>
              <span className={styles.kitMeta}>v1 · Applied · {shown.plan.length} resources</span>
            </span>
          </div>
        )}
      </div>
    </figure>
  );
}
