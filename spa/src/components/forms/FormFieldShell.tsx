import type { ReactNode } from "react";
import { Label } from "../ui/label";
import type { FormInput } from "../../types/form";

interface FormFieldShellProps {
  field: FormInput;
  children: ReactNode;
}

export function FormFieldShell({ field, children }: FormFieldShellProps) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex min-w-0 flex-col gap-1">
        <Label htmlFor={field.name} className="text-sm font-medium leading-5 text-[var(--text-primary)]">
          {field.label}
        </Label>
        {field.attr?.help_text && (
          <p className="text-xs leading-5 text-[var(--text-muted)]">
            {field.attr.help_text}
          </p>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        {children}
      </div>
    </div>
  );
}
