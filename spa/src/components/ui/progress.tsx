import * as React from "react";
import { cn } from "../../lib/utils";

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
    sm: "h-1",
    default: "h-2",
    lg: "h-3",
  };

  return (
    <div className={className}>
      {showLabel && (
        <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
          <span>{label ?? "Progress"}</span>
          <span>
            {value} / {max}
          </span>
        </div>
      )}
      <div
        className={cn(
          "bg-[var(--bg-tertiary)] rounded-full overflow-hidden",
          heights[size]
        )}
      >
        <div
          className="h-full bg-gradient-to-r from-[var(--gradient-start)] to-[var(--gradient-mid)] transition-all duration-300"
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
    <div className={cn("relative inline-flex", className)}>
      <svg width={size} height={size} className="transform -rotate-90">
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
          className="transition-all duration-300"
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-[var(--text-primary)]">
        {Math.round(percentage)}%
      </span>
    </div>
  );
}

export { ProgressBar, CircularProgress };
