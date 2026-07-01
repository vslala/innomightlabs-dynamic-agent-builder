import * as React from "react";
import { cn } from "../../lib/utils";

type Gap = "none" | "xs" | "sm" | "md" | "lg" | "xl";

const gapStyles: Record<Gap, React.CSSProperties> = {
  none: { gap: "var(--space-0)" },
  xs: { gap: "var(--space-2)" },
  sm: { gap: "var(--space-3)" },
  md: { gap: "var(--space-5)" },
  lg: { gap: "var(--space-6)" },
  xl: { gap: "var(--space-8)" },
};

export interface StackProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: Gap;
}

export function Stack({ className, gap = "md", style, ...props }: StackProps) {
  return (
    <div
      className={cn("flex min-w-0 flex-col", className)}
      style={{ ...gapStyles[gap], ...style }}
      {...props}
    />
  );
}

export interface InlineProps extends React.HTMLAttributes<HTMLDivElement> {
  gap?: Gap;
  align?: React.CSSProperties["alignItems"];
  justify?: React.CSSProperties["justifyContent"];
  wrap?: boolean;
}

export function Inline({
  className,
  gap = "sm",
  align = "center",
  justify,
  wrap = true,
  style,
  ...props
}: InlineProps) {
  return (
    <div
      className={cn("flex min-w-0", className)}
      style={{
        ...gapStyles[gap],
        alignItems: align,
        justifyContent: justify,
        flexWrap: wrap ? "wrap" : "nowrap",
        ...style,
      }}
      {...props}
    />
  );
}
