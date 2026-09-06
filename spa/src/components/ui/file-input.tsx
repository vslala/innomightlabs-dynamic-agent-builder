import * as React from "react";
import { cn } from "../../lib/utils";
import styles from "./file-input.module.css";

export interface FileInputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const FileInput = React.forwardRef<HTMLInputElement, FileInputProps>(
  ({ className, type: _type, ...props }, ref) => (
    <input
      ref={ref}
      type="file"
      className={cn(styles.fileInput, className)}
      {...props}
    />
  )
);
FileInput.displayName = "FileInput";

export { FileInput };
