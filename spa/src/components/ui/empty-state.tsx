import { cn } from "../../lib/utils";
import { Card, CardContent } from "./card";
import { Button } from "./button";
import type { LucideIcon } from "lucide-react";
import styles from "./empty-state.module.css";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}

function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
}: EmptyStateProps) {
  return (
    <Card className={className}>
      <CardContent className={styles.content}>
        <div className={styles.centered}>
          <Icon className={styles.icon} />
          <h3 className={styles.title}>
            {title}
          </h3>
          <p className={styles.description}>
            {description}
          </p>
          {actionLabel && onAction && (
            <Button onClick={onAction}>{actionLabel}</Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

interface InlineEmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  className?: string;
}

function InlineEmptyState({
  icon: Icon,
  title,
  description,
  className,
}: InlineEmptyStateProps) {
  return (
    <div className={cn(styles.inlineContainer, className)}>
      <Icon className={styles.inlineIcon} />
      <p className={styles.inlineTitle}>{title}</p>
      {description && (
        <p className={styles.inlineDescription}>{description}</p>
      )}
    </div>
  );
}

export { EmptyState, InlineEmptyState };
