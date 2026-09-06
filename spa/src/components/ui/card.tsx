import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./card.module.css";

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, style, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.card, className)}
    style={{ boxShadow: "0 1px 2px var(--shadow-soft)", ...style }}
    {...props}
  />
));
Card.displayName = "Card";

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, style, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.cardHeader, className)}
    style={{ gap: "var(--space-2)", padding: "var(--card-padding)", paddingBottom: "var(--space-3)", ...style }}
    {...props}
  />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.cardTitle, className)}
    {...props}
  />
));
CardTitle.displayName = "CardTitle";

const CardDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.cardDescription, className)}
    {...props}
  />
));
CardDescription.displayName = "CardDescription";

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, style, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("", className)}
    style={{ padding: "var(--card-padding)", paddingTop: "var(--space-3)", ...style }}
    {...props}
  />
));
CardContent.displayName = "CardContent";

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, style, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(styles.cardFooter, className)}
    style={{ gap: "var(--space-3)", padding: "var(--card-padding)", paddingTop: "var(--space-3)", ...style }}
    {...props}
  />
));
CardFooter.displayName = "CardFooter";

interface PanelProps extends React.HTMLAttributes<HTMLDivElement> {
  density?: "compact" | "default" | "spacious";
}

const panelPadding: Record<NonNullable<PanelProps["density"]>, string> = {
  compact: "var(--space-4)",
  default: "var(--card-padding)",
  spacious: "var(--card-padding-lg)",
};

const Panel = React.forwardRef<HTMLDivElement, PanelProps>(
  ({ className, density = "default", style, ...props }, ref) => (
    <Card
      ref={ref}
      className={cn(styles.panel, className)}
      style={{ "--panel-padding": panelPadding[density], ...style } as React.CSSProperties}
      {...props}
    />
  )
);
Panel.displayName = "Panel";

const PanelHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, style, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(styles.panelHeader, className)}
      style={{
        gap: "var(--space-4)",
        padding: "var(--panel-padding, var(--card-padding))",
        paddingBottom: "var(--space-3)",
        ...style,
      }}
      {...props}
    />
  )
);
PanelHeader.displayName = "PanelHeader";

const PanelBody = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, style, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(styles.panelBody, className)}
      style={{
        padding: "var(--panel-padding, var(--card-padding))",
        paddingTop: "var(--space-3)",
        ...style,
      }}
      {...props}
    />
  )
);
PanelBody.displayName = "PanelBody";

const PanelFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, style, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(styles.panelFooter, className)}
      style={{
        gap: "var(--space-3)",
        padding: "var(--panel-padding, var(--card-padding))",
        paddingTop: "var(--space-3)",
        ...style,
      }}
      {...props}
    />
  )
);
PanelFooter.displayName = "PanelFooter";

const PanelTitle = CardTitle;
const PanelDescription = CardDescription;

interface SectionCardHeaderProps {
  icon: React.ComponentType<{ className?: string }>;
  title: React.ReactNode;
  status?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

function SectionCardHeader({ icon: Icon, title, status, action, className }: SectionCardHeaderProps) {
  return (
    <div className={cn(styles.sectionHeader, className)} style={{ gap: "var(--space-4)" }}>
      <div className={styles.sectionHeaderLeft} style={{ gap: "var(--space-2)" }}>
        <Icon className={styles.sectionHeaderIcon} />
        <CardTitle className={styles.sectionHeaderTitle}>{title}</CardTitle>
        {status}
      </div>
      {action && (
        <div className={styles.sectionHeaderActions} style={{ gap: "var(--space-2)" }}>
          {action}
        </div>
      )}
    </div>
  );
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardDescription,
  CardContent,
  Panel,
  PanelHeader,
  PanelBody,
  PanelFooter,
  PanelTitle,
  PanelDescription,
  SectionCardHeader,
};
