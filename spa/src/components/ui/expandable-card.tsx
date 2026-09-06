import * as React from "react";
import { cn } from "../../lib/utils";
import { ChevronDown, ChevronRight } from "lucide-react";
import styles from "./expandable-card.module.css";

interface ExpandableCardProps {
  expanded: boolean;
  onToggle: () => void;
  header: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
}

function ExpandableCard({
  expanded,
  onToggle,
  header,
  children,
  className,
  headerClassName,
  contentClassName,
}: ExpandableCardProps) {
  return (
    <div
      className={cn(styles.card, className)}
    >
      <div
        className={cn(styles.header, headerClassName)}
        style={{ padding: "var(--space-5)" }}
        onClick={onToggle}
      >
        <span className={styles.chevron}>
          {expanded ? (
            <ChevronDown className={styles.chevronIcon} />
          ) : (
            <ChevronRight className={styles.chevronIcon} />
          )}
        </span>
        <div className={styles.headerContent}>{header}</div>
      </div>

      {expanded && (
        <div
          className={cn(styles.content, contentClassName)}
          style={{ padding: "var(--space-5)" }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

interface CollapsibleSectionProps {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  icon?: React.ReactNode;
}

function CollapsibleSection({
  title,
  defaultExpanded = false,
  children,
  className,
  headerClassName,
  icon,
}: CollapsibleSectionProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);

  return (
    <div className={cn(styles.section, className)}>
      <button
        type="button"
        className={cn(styles.sectionHeader, headerClassName)}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className={styles.sectionChevronIcon} />
        ) : (
          <ChevronRight className={styles.sectionChevronIcon} />
        )}
        {icon}
        {title}
      </button>
      {expanded && <div>{children}</div>}
    </div>
  );
}

export { ExpandableCard, CollapsibleSection };
