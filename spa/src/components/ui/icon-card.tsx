import * as React from "react";
import { cn } from "../../lib/utils";
import { Card, CardContent } from "./card";
import type { LucideIcon } from "lucide-react";
import styles from "./icon-card.module.css";

interface IconCardProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  footer?: React.ReactNode;
  actions?: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

function IconCard({
  icon: Icon,
  title,
  description,
  footer,
  actions,
  onClick,
  className,
}: IconCardProps) {
  return (
    <Card
      className={cn(
        "group",
        styles.card,
        onClick && styles.cardCursor,
        className
      )}
      onClick={onClick}
    >
      <CardContent className={styles.cardContent}>
        <div className={styles.cardTop}>
          <div className={styles.iconBox}>
            <Icon className={styles.icon} />
          </div>
          {actions && (
            <div className={styles.actions}>
              {actions}
            </div>
          )}
        </div>

        <h3 className={styles.title}>
          {title}
        </h3>
        {description && (
          <p className={styles.description}>
            {description}
          </p>
        )}
        {footer}
      </CardContent>
    </Card>
  );
}

interface IconHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  size?: "sm" | "default" | "lg";
  className?: string;
}

function IconHeader({
  icon: Icon,
  title,
  subtitle,
  actions,
  size = "default",
  className,
}: IconHeaderProps) {
  const sizes = {
    sm: { container: styles.iconContainerSm, icon: styles.iconSm, title: styles.titleSm, subtitle: styles.subtitleSm },
    default: { container: styles.iconContainerDefault, icon: styles.iconDefault, title: styles.titleDefault, subtitle: styles.subtitleDefault },
    lg: { container: styles.iconContainerLg, icon: styles.iconLg, title: styles.titleLg, subtitle: styles.subtitleLg },
  };

  const s = sizes[size];

  return (
    <div className={cn(styles.header, className)}>
      <div className={styles.headerLeft}>
        <div
          className={cn(
            styles.headerIconBox,
            s.container
          )}
        >
          <Icon className={cn(styles.headerIcon, s.icon)} />
        </div>
        <div>
          <h1 className={cn(styles.headerTitle, s.title)}>
            {title}
          </h1>
          {subtitle && (
            <p className={cn(styles.headerSubtitle, s.subtitle)}>
              {subtitle}
            </p>
          )}
        </div>
      </div>
      {actions}
    </div>
  );
}

export { IconCard, IconHeader };
