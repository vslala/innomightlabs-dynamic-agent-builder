import * as React from "react";
import { cn } from "../../lib/utils";

export interface FileInputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const FileInput = React.forwardRef<HTMLInputElement, FileInputProps>(
  ({ className, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="file"
      className={cn("sr-only", className)}
      {...props}
    />
  )
);
FileInput.displayName = "FileInput";

export { FileInput };
