import { useEffect, useState } from "react";

import { SchemaForm } from "../../../components/forms/SchemaForm";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  LoadingState,
} from "../../../components/ui";
import type { FormSchema, FormValue } from "../../../types/form";

interface SchemaFormDialogProps {
  title: string;
  description: string;
  submitLabel: string;
  loadSchema: () => Promise<FormSchema>;
  onSubmit: (values: Record<string, string>) => Promise<void>;
  onClose: () => void;
}

/** A backend-described form in a dialog: the provider owns the fields, the SPA only renders them. */
export function SchemaFormDialog({ title, description, submitLabel, loadSchema, onSubmit, onClose }: SchemaFormDialogProps) {
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadSchema()
      .then((loaded) => active && setSchema(loaded))
      .catch((err: unknown) => active && setError(err instanceof Error ? err.message : "Failed to load the form."));
    return () => {
      active = false;
    };
    // The dialog is mounted per provider/connection, so the loader is fixed for its lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (data: Record<string, FormValue>) => {
    setSaving(true);
    setError(null);
    try {
      await onSubmit(stringValues(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && !saving && onClose()}>
      <DialogContent style={{ maxWidth: "36rem" }}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {schema ? (
          <SchemaForm
            schema={schema}
            onSubmit={submit}
            onCancel={onClose}
            submitLabel={submitLabel}
            isLoading={saving}
            actionAlign="end"
          />
        ) : (
          !error && <LoadingState />
        )}
        {error && <div style={{ color: "var(--error)", fontSize: "0.875rem" }}>{error}</div>}
      </DialogContent>
    </Dialog>
  );
}

function stringValues(data: Record<string, FormValue>): Record<string, string> {
  const values: Record<string, string> = {};
  for (const [name, value] of Object.entries(data)) {
    if (typeof value === "string") values[name] = value;
  }
  return values;
}
