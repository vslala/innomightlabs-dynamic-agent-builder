import * as React from "react";
import { cn } from "../../lib/utils";

export interface RadioProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Radio = React.forwardRef<HTMLInputElement, RadioProps>(
  ({ className, style, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="radio"
      className={cn(
        "shrink-0 border border-[var(--border-default)] bg-[var(--surface-control)] accent-[var(--gradient-start)] disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      style={{ height: "1rem", width: "1rem", ...style }}
      {...props}
    />
  )
);
Radio.displayName = "Radio";

export { Radio };
