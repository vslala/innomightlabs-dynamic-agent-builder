import type { ReactNode } from "react";
import { Label } from "../ui/label";
import { FieldGroup, Stack } from "../layout";
import type { FormInput } from "../../types/form";

interface FormFieldShellProps {
  field: FormInput;
  children: ReactNode;
}

export function FormFieldShell({ field, children }: FormFieldShellProps) {
  return (
    <FieldGroup>
      <Stack gap="xs">
        <Label htmlFor={field.name} className="text-sm font-medium leading-5 text-[var(--text-primary)]">
          {field.label}
        </Label>
        {field.attr?.help_text && (
          <p className="text-xs leading-5 text-[var(--text-muted)]">
            {field.attr.help_text}
          </p>
        )}
      </Stack>
      <Stack gap="xs">
        {children}
      </Stack>
    </FieldGroup>
  );
}
