import * as React from "react";
import { cn } from "../../lib/utils";

interface StatItemProps {
  label: string;
  value: string | number;
  valueClassName?: string;
  className?: string;
}

function StatItem({ label, value, valueClassName, className }: StatItemProps) {
  return (
    <div className={className}>
      <p className="text-xs text-[var(--text-muted)]">{label}</p>
      <p className={cn("text-lg font-semibold text-[var(--text-primary)]", valueClassName)}>
        {value}
      </p>
    </div>
  );
}

interface StatsGridProps {
  children: React.ReactNode;
  columns?: 2 | 3 | 4;
  className?: string;
}

function StatsGrid({ children, columns = 4, className }: StatsGridProps) {
  const gridCols = {
    2: "grid-cols-2",
    3: "grid-cols-2 md:grid-cols-3",
    4: "grid-cols-2 md:grid-cols-4",
  };

  return (
    <div className={cn("grid gap-4", gridCols[columns], className)}>
      {children}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}

function StatCard({ label, value, icon, trend, className }: StatCardProps) {
  return (
    <div
      className={cn(
        "p-4 rounded-lg border border-[var(--border-subtle)] bg-white/[0.02]",
        className
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-[var(--text-muted)]">{label}</span>
        {icon && <span className="text-[var(--text-muted)]">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-[var(--text-primary)]">
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              "text-xs font-medium",
              trend.isPositive ? "text-green-400" : "text-red-400"
            )}
          >
            {trend.isPositive ? "+" : "-"}
            {Math.abs(trend.value)}%
          </span>
        )}
      </div>
    </div>
  );
}

export { StatItem, StatsGrid, StatCard };
