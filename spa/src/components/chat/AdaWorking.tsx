import { ADA_STEPS, type AdaStep } from "./adaSteps";
import styles from "./AdaWorking.module.css";

/** One small drawing per step, sketched over and over on a blueprint tile while Ada works. */
const SKETCHES: Record<AdaStep, string[]> = {
  thinking: ["M10 24 Q18 10 26 24 T42 24", "M14 30 H38"],
  asking: ["M12 12 H40 M12 20 H32", "M12 28 H40 V34 H12 Z"],
  drafting: ["M6 14 H18 V28 H6 Z", "M30 10 H44 V22 H30 Z", "M30 26 H44 V36 H30 Z", "M18 21 C24 21 24 16 30 16", "M18 21 C24 21 24 31 30 31"],
  building: ["M8 34 H44", "M12 34 V24 H22 V34", "M24 34 V18 H34 V34", "M36 34 V12 H44 V34"],
  checking: ["M26 10 A14 14 0 1 1 12 24", "M26 24 L33 17", "M26 24 m-2 0 a2 2 0 1 0 4 0 a2 2 0 1 0 -4 0"],
};

export function AdaWorking({ step }: { step: AdaStep }) {
  const copy = ADA_STEPS[step];
  return (
    <div className={styles.card} role="status" aria-live="polite">
      <svg key={step} className={styles.tile} viewBox="0 0 52 44" aria-hidden="true">
        {SKETCHES[step].map((d, index) => (
          <path key={d} d={d} pathLength={1} className={styles.stroke} style={{ animationDelay: `${index * 0.35}s` }} />
        ))}
      </svg>
      <div className={styles.text}>
        <span className={styles.title}>
          {copy.title}
          <span className={styles.dots} aria-hidden="true">
            <span>.</span>
            <span>.</span>
            <span>.</span>
          </span>
        </span>
        <span className={styles.detail}>{copy.detail}</span>
      </div>
    </div>
  );
}
