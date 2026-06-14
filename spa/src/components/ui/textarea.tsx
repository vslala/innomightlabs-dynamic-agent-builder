import * as React from "react";
import { cn } from "../../lib/utils";

const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<"textarea">
>(({ className, autoComplete, style, ...props }, ref) => {
  return (
    <textarea
      autoComplete={autoComplete ?? "off"}
      className={cn(
        "flex min-h-[96px] w-full rounded-lg border border-[var(--border-subtle)] bg-white/5 px-4 py-3 text-sm leading-6 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--gradient-start)]/50 focus:border-[var(--gradient-start)] disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200 resize-none",
        className
      )}
      style={{
        paddingInline: "1rem",
        paddingBlock: "0.75rem",
        boxSizing: "border-box",
        ...style,
      }}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = "Textarea";

export { Textarea };
