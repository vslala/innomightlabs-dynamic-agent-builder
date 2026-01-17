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

import { useState, useEffect } from "react";
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

export function SchemaForm({
  schema,
  initialValues = {},
  onSubmit,
  onCancel,
  submitLabel = "Submit",
  cancelLabel = "Cancel",
  isLoading = false,
}: SchemaFormProps) {
  // Initialize form state from schema fields
  const [formData, setFormData] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    schema.form_inputs.forEach((field) => {
      initial[field.name] = initialValues[field.name] || field.value || "";
    });
    return initial;
  });

  // Update form data when initialValues change
  useEffect(() => {
    const updated: Record<string, string> = {};
    schema.form_inputs.forEach((field) => {
      updated[field.name] = initialValues[field.name] || field.value || "";
    });
    setFormData(updated);
  }, [initialValues, schema.form_inputs]);

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
    <form onSubmit={handleSubmit} className="space-y-6">
      {schema.form_inputs.map((field) => (
        <FormField
          key={field.name}
          field={field}
          value={formData[field.name] || ""}
          onChange={(value) => handleFieldChange(field.name, value)}
        />
      ))}

      <div className="flex gap-3 pt-4">
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
        <Button type="submit" disabled={isLoading} className="flex-1">
          {isLoading ? "Loading..." : submitLabel}
        </Button>
      </div>
    </form>
  );
}
