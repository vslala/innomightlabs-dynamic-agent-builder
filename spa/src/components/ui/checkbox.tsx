import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./checkbox.module.css";

export interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Checkbox = React.forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, style, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="checkbox"
      className={cn(styles.checkbox, className)}
      style={{ height: "1rem", width: "1rem", ...style }}
      {...props}
    />
  )
);
Checkbox.displayName = "Checkbox";

export { Checkbox };
