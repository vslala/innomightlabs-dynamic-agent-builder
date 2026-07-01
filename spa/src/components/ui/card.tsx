import * as React from "react";
import { cn } from "../../lib/utils";

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-lg border border-[var(--border-default)] bg-[var(--surface-panel)]",
      className
    )}
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
    className={cn("flex flex-col", className)}
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
    className={cn(
      "text-base font-semibold leading-none tracking-tight text-[var(--text-primary)]",
      className
    )}
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
    className={cn("text-sm text-[var(--text-muted)]", className)}
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
    className={cn("flex items-center", className)}
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
      className={cn("min-w-0", className)}
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
      className={cn("flex min-w-0 items-start justify-between", className)}
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
      className={cn("min-w-0", className)}
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
      className={cn("flex flex-wrap items-center justify-end", className)}
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
};
