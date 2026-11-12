import { useEffect, useState } from "react";
import { SchemaForm } from "../../../../components/forms";
import { Spinner } from "../../../../components/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../../../components/ui/dialog";
import { builderApiService } from "../../../../services/builder/BuilderApiService";
import type { FormSchema, FormValue } from "../../../../types/form";
import styles from "./ConversationDialogs.module.css";

interface ChangeIlaModelDialogProps {
  conversationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ChangeIlaModelDialog({ open, onOpenChange, ...props }: ChangeIlaModelDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounted only while open, so the form and the current model are read fresh each time */}
      {open && <ChangeIlaModelForm onClose={() => onOpenChange(false)} {...props} />}
    </Dialog>
  );
}

function ChangeIlaModelForm({ conversationId, onClose }: Omit<ChangeIlaModelDialogProps, "open" | "onOpenChange"> & { onClose: () => void }) {
  const [form, setForm] = useState<FormSchema | null>(null);
  const [current, setCurrent] = useState<Record<string, FormValue>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([builderApiService.getSessionForm(), builderApiService.getSession(conversationId)])
      .then(([schema, session]) => {
        setCurrent({ agent_provider: session.provider, agent_model: session.model ?? "" });
        setForm(schema);
      })
      .catch((err) => {
        console.error("Error loading Ila's model:", err);
        setError("Couldn't load the models. Please try again.");
      });
  }, [conversationId]);

  const save = async (values: Record<string, FormValue>) => {
    const provider = typeof values.agent_provider === "string" ? values.agent_provider : "";
    const model = typeof values.agent_model === "string" ? values.agent_model : "";
    setSaving(true);
    setError(null);
    try {
      await builderApiService.changeModel(conversationId, provider, model);
      onClose();
    } catch (err) {
      console.error("Error changing Ila's model:", err);
      setError(err instanceof Error ? err.message : "Couldn't change the model. Please try again.");
      setSaving(false);
    }
  };

  return (
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Change Ila&apos;s model</DialogTitle>
        <DialogDescription>
          Ila thinks with the model you choose from her next message. What you have built and planned stays as it is.
        </DialogDescription>
      </DialogHeader>
      <div className={styles.fields}>
        {!form && !error && (
          <p role="status">
            <Spinner size="sm" aria-hidden="true" /> Loading your models…
          </p>
        )}
        {form && (
          <SchemaForm
            schema={form}
            initialValues={current}
            onSubmit={save}
            onCancel={onClose}
            submitLabel={saving ? "Saving…" : "Change model"}
            isLoading={saving}
          />
        )}
        {error && <p className={styles.error} role="alert">{error}</p>}
      </div>
    </DialogContent>
  );
}
