import * as React from "react";
import { cn } from "../../lib/utils";

export function Page({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("min-w-0", className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--page-gap)", ...style }}
      {...props}
    />
  );
}

export function PageHeader({
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
        gap: "var(--space-5)",
        ...style,
      }}
      {...props}
    />
  );
}

export function PageTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h1
      className={cn("text-2xl font-semibold leading-tight text-[var(--text-primary)]", className)}
      {...props}
    />
  );
}

export function PageDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-sm leading-6 text-[var(--text-muted)]", className)}
      {...props}
    />
  );
}

export function PageActions({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("flex shrink-0 flex-wrap items-center justify-end", className)}
      style={{ gap: "var(--space-3)", ...style }}
      {...props}
    />
  );
}

export function PageBody({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("min-w-0", className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--section-gap)", ...style }}
      {...props}
    />
  );
}
