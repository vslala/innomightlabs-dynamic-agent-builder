import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./radio.module.css";

export interface RadioProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Radio = React.forwardRef<HTMLInputElement, RadioProps>(
  ({ className, style, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="radio"
      className={cn(
        styles.radio,
        className
      )}
      style={{ height: "1rem", width: "1rem", ...style }}
      {...props}
    />
  )
);
Radio.displayName = "Radio";

export { Radio };
