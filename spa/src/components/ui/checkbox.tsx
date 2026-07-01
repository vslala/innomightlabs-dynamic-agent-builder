import * as React from "react";
import { cn } from "../../lib/utils";

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, style, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn(
        "shrink-0 rounded border border-[var(--border-default)] bg-[var(--surface-control)] accent-[var(--gradient-start)] disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      style={{ height: "1rem", width: "1rem", ...style }}
      {...props}
    />
  )
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
