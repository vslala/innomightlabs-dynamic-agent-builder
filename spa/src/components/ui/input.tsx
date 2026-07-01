import * as React from "react";
import { cn } from "../../lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, autoComplete, style, ...props }, ref) => {
    return (
      <input
        type={type}
        autoComplete={autoComplete ?? "off"}
        className={cn(
          "flex w-full rounded-lg border border-[var(--border-default)] bg-[var(--surface-control)] text-sm leading-5 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--gradient-start)]/50 focus:border-[var(--gradient-start)] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200",
          className
        )}
        style={{
          minHeight: "var(--control-height-md)",
          paddingInline: "var(--control-padding-x-sm)",
          paddingBlock: "var(--space-3)",
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
