import * as React from "react";
import { cn } from "../../lib/utils";

interface ReadOnlyContentProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "plain" | "code" | "instructions";
  selectable?: boolean;
  children: React.ReactNode;
}

const variantClassName = {
  plain: "font-sans text-sm leading-7",
  code: "font-mono text-sm leading-7",
  instructions: "font-mono text-sm leading-7",
};

export function ReadOnlyContent({
  className,
  style,
  variant = "plain",
  selectable = true,
  children,
  ...props
}: ReadOnlyContentProps) {
  return (
    <div
      className={cn(
        "min-w-0 rounded-lg border border-[var(--border-default)] bg-[var(--surface-control)] text-[var(--text-secondary)]",
        variantClassName[variant],
        className
      )}
      style={{
        boxSizing: "border-box",
        maxWidth: "100%",
        overflowX: "auto",
        padding: "var(--space-5)",
        whiteSpace: "pre-wrap",
        userSelect: selectable ? "text" : "none",
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
}
