import { cn } from "../../lib/utils";
import styles from "./progress.module.css";

interface ProgressBarProps {
  value: number;
  max?: number;
  label?: string;
  showLabel?: boolean;
  className?: string;
  size?: "sm" | "default" | "lg";
}

function ProgressBar({
  value,
  max = 100,
  label,
  showLabel = true,
  className,
  size = "default",
}: ProgressBarProps) {
  const percentage = max > 0 ? Math.min((value / max) * 100, 100) : 0;

  const heights = {
    sm: styles.trackSm,
    default: styles.trackDefault,
    lg: styles.trackLg,
  };

  return (
    <div className={className}>
      {showLabel && (
        <div className={styles.labelRow}>
          <span>{label ?? "Progress"}</span>
          <span>
            {value} / {max}
          </span>
        </div>
      )}
      <div
        className={cn(
          styles.track,
          heights[size]
        )}
      >
        <div
          className={styles.fill}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

interface CircularProgressProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  className?: string;
}

function CircularProgress({
  value,
  max = 100,
  size = 48,
  strokeWidth = 4,
  className,
}: CircularProgressProps) {
  const percentage = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className={cn(styles.circularWrap, className)}>
      <svg width={size} height={size} className={styles.circularSvg}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="var(--bg-tertiary)"
          strokeWidth={strokeWidth}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="var(--gradient-start)"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className={styles.circularRing}
        />
      </svg>
      <span className={styles.circularLabel}>
        {Math.round(percentage)}%
      </span>
    </div>
  );
}

export { ProgressBar, CircularProgress };
