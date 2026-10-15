import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Archive, ArchiveRestore, Save, Trash2 } from "lucide-react";
import { ChatFormRenderer } from "../../../components/chat/ChatFormRenderer";
import { FormInputEditor } from "../../../components/forms/FormInputEditor";
import { FieldGroup } from "../../../components/layout";
import {
  Alert,
  AlertDescription,
  Button,
  ConfirmationDialog,
  Input,
  Label,
  Spinner,
  Textarea,
} from "../../../components/ui";
import { leadsApiService } from "../../../services/leads";
import type { FormInput } from "../../../types/form";
import type { LeadForm } from "../../../types/leads";
import { leadsErrorMessage } from "./errors";
import { macroFor, slugFrom } from "./leads";
import styles from "./Leads.module.css";

const STARTER_INPUTS: FormInput[] = [
  { input_type: "text", name: "name", label: "Full name" },
  { input_type: "text", name: "email", label: "Email", validation: { format: "email" } },
];

interface Draft {
  name: string;
  slug: string;
  purpose: string;
  inputs: FormInput[];
}

/** Creates a form at /forms/new and edits one at /forms/:formId. */
export function FormEditorPage() {
  const { formId } = useParams();
  const navigate = useNavigate();
  const [saved, setSaved] = useState<LeadForm | null>(null);
  const [draft, setDraft] = useState<Draft>({ name: "", slug: "", purpose: "", inputs: STARTER_INPUTS });
  const [slugEdited, setSlugEdited] = useState(false);
  const [loading, setLoading] = useState(Boolean(formId));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (!formId) return;
    leadsApiService.getForm(formId)
      .then((form) => {
        setSaved(form);
        setDraft({ name: form.name, slug: form.slug, purpose: form.purpose ?? "", inputs: form.form_inputs });
      })
      .catch((err) => setError(leadsErrorMessage(err, "This form couldn't be loaded.")))
      .finally(() => setLoading(false));
  }, [formId]);

  const run = async (action: () => Promise<void>, failure: string) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(leadsErrorMessage(err, failure));
    } finally {
      setBusy(false);
    }
  };

  const save = () => run(async () => {
    const fields = { name: draft.name, purpose: draft.purpose || null, form_inputs: draft.inputs };
    if (saved) {
      setSaved(await leadsApiService.updateForm(saved.form_id, fields));
    } else {
      const created = await leadsApiService.createForm({ ...fields, slug: draft.slug });
      navigate(`/dashboard/leads/forms/${created.form_id}`, { replace: true });
    }
  }, "The form couldn't be saved.");

  const archiveOrRestore = () => run(async () => {
    if (!saved) return;
    setSaved(saved.status === "active"
      ? await leadsApiService.archiveForm(saved.form_id)
      : await leadsApiService.restoreForm(saved.form_id));
  }, "The form couldn't be changed.");

  const remove = () => run(async () => {
    if (!saved) return;
    setConfirmingDelete(false);
    await leadsApiService.deleteForm(saved.form_id);
    navigate("/dashboard/leads/forms");
  }, "The form couldn't be deleted.");

  if (loading) return <p role="status" className={styles.muted}><Spinner size="sm" aria-hidden="true" /> Loading form…</p>;

  return (
    <section className={styles.content} aria-labelledby="form-heading">
      <div className={styles.toolbar}>
        <h2 id="form-heading" className={styles.heading}>{saved ? saved.name : "New lead form"}</h2>
        <div className={styles.actions}>
          {saved && (
            <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => void archiveOrRestore()}>
              {saved.status === "active"
                ? <><Archive aria-hidden="true" />Archive</>
                : <><ArchiveRestore aria-hidden="true" />Restore</>}
            </Button>
          )}
          {saved && saved.capture_count === 0 && (
            <Button type="button" variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmingDelete(true)}>
              <Trash2 aria-hidden="true" />Delete
            </Button>
          )}
          <Button type="button" size="sm" disabled={busy || !draft.name || !draft.slug} onClick={() => void save()}>
            <Save aria-hidden="true" />{saved ? "Save" : "Create form"}
          </Button>
        </div>
      </div>
      {error && <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>}
      {saved?.status === "archived" && (
        <Alert variant="info"><AlertDescription>Archived: agents no longer collect this form. Its leads are kept.</AlertDescription></Alert>
      )}

      <div className={styles.editorLayout}>
        <div className={styles.content}>
          <div className={styles.panel}>
            <div className={styles.panelBody}>
              <FieldGroup>
                <Label htmlFor="lead-form-name">Name</Label>
                <Input id="lead-form-name" value={draft.name} placeholder="Demo request"
                  onChange={(e) => setDraft({ ...draft, name: e.target.value, slug: saved || slugEdited ? draft.slug : slugFrom(e.target.value) })} />
              </FieldGroup>
              <FieldGroup>
                <Label htmlFor="lead-form-slug">Slug</Label>
                <Input id="lead-form-slug" value={draft.slug} disabled={Boolean(saved)} className={styles.mono}
                  onChange={(e) => { setSlugEdited(true); setDraft({ ...draft, slug: e.target.value }); }} />
                <p className={styles.muted}>
                  {saved ? "Agents name the form by its slug, so it can't change." : "Agents name the form by this. It can't change later."}
                </p>
              </FieldGroup>
              <FieldGroup>
                <Label htmlFor="lead-form-purpose">Why you collect this</Label>
                <Textarea id="lead-form-purpose" rows={2} value={draft.purpose}
                  placeholder="Understand what the visitor needs so sales can follow up."
                  onChange={(e) => setDraft({ ...draft, purpose: e.target.value })} />
              </FieldGroup>
              {draft.slug && (
                <div className={styles.macro}>
                  <span className={styles.muted}>Put this in an agent's instructions</span>
                  <code className={styles.mono}>{macroFor(draft.slug)}</code>
                </div>
              )}
            </div>
          </div>
          <FormInputEditor inputs={draft.inputs} onChange={(inputs) => setDraft({ ...draft, inputs })} disabled={busy} agentHints />
        </div>

        <aside className={styles.panel} aria-label="Preview">
          <div className={styles.panelBody}>
            <p className={styles.muted}>What a person sees when the agent shows the form</p>
            <ChatFormRenderer
              form={{ form_name: draft.name || "Untitled form", submit_path: "", form_inputs: draft.inputs }}
              onSubmit={() => undefined}
              disabled
            />
          </div>
        </aside>
      </div>

      <ConfirmationDialog
        open={confirmingDelete}
        onOpenChange={setConfirmingDelete}
        title="Delete this form?"
        description="Agents whose instructions name it will be told it doesn't exist."
        confirmText="Delete"
        variant="destructive"
        onConfirm={remove}
      />
    </section>
  );
}
