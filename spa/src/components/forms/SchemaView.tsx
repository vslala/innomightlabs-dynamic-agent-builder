/**
 * SchemaView component - renders a read-only view of data based on a schema.
 *
 * Usage:
 * ```tsx
 * <SchemaView
 *   schema={formSchema}
 *   data={agentData}
 * />
 * ```
 */

import { ViewField } from "./ViewField";
import type { FormSchema } from "../../types/form";

interface SchemaViewProps {
  schema: FormSchema;
  data: Record<string, unknown>;
}

export function SchemaView({ schema, data }: SchemaViewProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {schema.form_inputs.map((field) => {
        const value = data[field.name];
        const displayValue = value != null ? String(value) : "";

        return (
          <ViewField
            key={field.name}
            field={field}
            value={displayValue}
          />
        );
      })}
    </div>
  );
}
