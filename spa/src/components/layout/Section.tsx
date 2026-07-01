import * as React from "react";
import { cn } from "../../lib/utils";

export function Section({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("min-w-0", className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", ...style }}
      {...props}
    />
  );
}

export function SectionHeader({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("min-w-0", className)}
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "var(--space-4)",
        ...style,
      }}
      {...props}
    />
  );
}

export function SectionTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("text-lg font-semibold leading-tight text-[var(--text-primary)]", className)}
      {...props}
    />
  );
}

export function SectionDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("text-sm leading-6 text-[var(--text-muted)]", className)} {...props} />
  );
}
