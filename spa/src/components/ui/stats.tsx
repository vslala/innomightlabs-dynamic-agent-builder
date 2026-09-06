import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./stats.module.css";

interface StatItemProps {
  label: string;
  value: string | number;
  valueClassName?: string;
  className?: string;
}

function StatItem({ label, value, valueClassName, className }: StatItemProps) {
  return (
    <div className={className}>
      <p className={styles.statLabel}>{label}</p>
      <p className={cn(styles.statValue, valueClassName)}>
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
    2: styles.gridCols2,
    3: styles.gridCols3,
    4: styles.gridCols4,
  };

  return (
    <div className={cn(styles.statsGrid, gridCols[columns], className)}>
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
      className={cn(styles.statCard, className)}
    >
      <div className={styles.statCardHeader}>
        <span className={styles.statCardLabel}>{label}</span>
        {icon && <span className={styles.statCardIcon}>{icon}</span>}
      </div>
      <div className={styles.statCardValueRow}>
        <span className={styles.statCardValue}>
          {value}
        </span>
        {trend && (
          <span
            className={cn(
              styles.statCardTrend,
              trend.isPositive ? styles.trendPositive : styles.trendNegative
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
