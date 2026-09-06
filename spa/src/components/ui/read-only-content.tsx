import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./read-only-content.module.css";

interface ReadOnlyContentProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "plain" | "code" | "instructions";
  selectable?: boolean;
  children: React.ReactNode;
}

const variantClassName = {
  plain: styles.variantPlain,
  code: styles.variantCode,
  instructions: styles.variantInstructions,
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
        styles.content,
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
