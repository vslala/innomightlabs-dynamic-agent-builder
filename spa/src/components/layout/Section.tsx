import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./Section.module.css";

export function Section({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn(styles.section, className)}
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
      className={cn(styles.sectionHeader, className)}
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
      className={cn(styles.sectionTitle, className)}
      {...props}
    />
  );
}

export function SectionDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn(styles.sectionDescription, className)} {...props} />
  );
}
