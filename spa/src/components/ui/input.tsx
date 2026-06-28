import * as React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, autoComplete, style, ...props }, ref) => {
    return (
      <input
        type={type}
        autoComplete={autoComplete ?? "off"}
        className={cn(
          "flex h-11 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2.5 text-sm leading-5 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--gradient-start)]/50 focus:border-[var(--gradient-start)] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200",
          className
        )}
        style={{
          paddingInline: "1rem",
          paddingBlock: "0.625rem",
          boxSizing: "border-box",
          ...style,
        }}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
