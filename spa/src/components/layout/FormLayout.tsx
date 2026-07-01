import * as React from "react";
import { cn } from "../../lib/utils";

export function FormStack({
  className,
  style,
  ...props
}: React.FormHTMLAttributes<HTMLFormElement>) {
  return (
    <form
      className={cn("min-w-0", className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--form-gap)", ...style }}
      {...props}
    />
  );
}

export function FieldGroup({
  className,
  style,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("min-w-0", className)}
      style={{ display: "flex", flexDirection: "column", gap: "var(--field-gap)", ...style }}
      {...props}
    />
  );
}

export function FormActions({
  className,
  style,
  align = "end",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: "start" | "end" | "stretch" }) {
  const justify = align === "start" ? "flex-start" : "flex-end";
  return (
    <div
      className={cn("flex flex-wrap items-center", className)}
      style={{
        gap: "var(--space-3)",
        justifyContent: justify,
        paddingTop: "var(--space-2)",
        ...(align === "stretch" ? { flexDirection: "column", alignItems: "stretch" } : null),
        ...style,
      }}
      {...props}
    />
  );
}
