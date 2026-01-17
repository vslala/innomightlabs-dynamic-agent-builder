/**
 * SchemaForm component - renders a form dynamically based on a schema.
 *
 * Usage:
 * ```tsx
 * <SchemaForm
 *   schema={formSchema}
 *   onSubmit={(data) => console.log(data)}
 *   submitLabel="Create"
 * />
 * ```
 */

import { useState } from "react";
import { Button } from "../ui/button";
import { FormField } from "./FormField";
import type { FormSchema } from "../../types/form";

interface SchemaFormProps {
  schema: FormSchema;
  initialValues?: Record<string, string>;
  onSubmit: (data: Record<string, string>) => void | Promise<void>;
  onCancel?: () => void;
  submitLabel?: string;
  cancelLabel?: string;
  isLoading?: boolean;
}

// Empty object constant to avoid creating new references
const EMPTY_INITIAL_VALUES: Record<string, string> = {};

export function SchemaForm({
  schema,
  initialValues,
  onSubmit,
  onCancel,
  submitLabel = "Submit",
  cancelLabel = "Cancel",
  isLoading = false,
}: SchemaFormProps) {
  // Memoize initial values to avoid reference changes
  const stableInitialValues = initialValues || EMPTY_INITIAL_VALUES;

  // Initialize form state from schema fields
  const [formData, setFormData] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    schema.form_inputs.forEach((field) => {
      initial[field.name] = stableInitialValues[field.name] || field.value || "";
    });
    return initial;
  });

  const handleFieldChange = (fieldName: string, value: string) => {
    setFormData((prev) => ({
      ...prev,
      [fieldName]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit(formData);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {schema.form_inputs.map((field) => (
        <FormField
          key={field.name}
          field={field}
          value={formData[field.name] || ""}
          onChange={(value) => handleFieldChange(field.name, value)}
        />
      ))}

      <div style={{ display: "flex", gap: "0.75rem", paddingTop: "1rem" }}>
        {onCancel && (
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={isLoading} style={{ flex: 1 }}>
          {isLoading ? "Loading..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
