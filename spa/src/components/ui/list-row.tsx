import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./list-row.module.css";

interface ListRowProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  meta?: React.ReactNode;
  trailing?: React.ReactNode;
  className?: string;
}

function ListRow({ icon, title, subtitle, meta, trailing, className }: ListRowProps) {
  return (
    <div
      className={cn(
        styles.row,
        className
      )}
      style={{ gap: "var(--space-5)", padding: "var(--space-4) var(--space-5)" }}
    >
      <div className={styles.rowLeft} style={{ gap: "var(--space-4)" }}>
        {icon && (
          <div className={styles.icon}>
            {icon}
          </div>
        )}
        <div className={styles.body}>
          <p className={styles.title}>{title}</p>
          {subtitle && (
            <p className={styles.subtitle} style={{ marginTop: "var(--space-1)" }}>
              {subtitle}
            </p>
          )}
          {meta && (
            <p
              className={styles.meta}
              style={{ marginTop: "var(--space-2)" }}
            >
              {meta}
            </p>
          )}
        </div>
      </div>
      {trailing && (
        <div className={styles.trailing}>{trailing}</div>
      )}
    </div>
  );
}

export { ListRow };
