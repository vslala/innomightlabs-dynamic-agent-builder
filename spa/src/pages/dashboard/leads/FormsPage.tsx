import { useEffect, useState } from "react";
import { Copy, FileText, Plus } from "lucide-react";
import { Alert, AlertDescription, Button, InlineEmptyState, LinkButton, Pill, Spinner } from "../../../components/ui";
import { leadsApiService } from "../../../services/leads";
import type { LeadForm } from "../../../types/leads";
import { leadsErrorMessage } from "./errors";
import { macroFor } from "./leads";
import styles from "./Leads.module.css";

export function FormsPage() {
  const [forms, setForms] = useState<LeadForm[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    leadsApiService.listForms()
      .then(setForms)
      .catch((err) => setError(leadsErrorMessage(err, "Lead forms couldn't be loaded.")));
  }, []);

  const copyMacro = async (slug: string) => {
    await navigator.clipboard.writeText(macroFor(slug));
    setCopied(slug);
  };

  return (
    <section className={styles.content} aria-labelledby="forms-heading">
      <div className={styles.toolbar}>
        <div>
          <h2 id="forms-heading" className={styles.heading}>Forms</h2>
          <p className={styles.muted}>
            An agent collects a form when its instructions name it. Copy a form's macro into the instructions, or ask
            Ila to set it up.
          </p>
        </div>
        <LinkButton to="/dashboard/leads/forms/new" size="sm"><Plus aria-hidden="true" />New form</LinkButton>
      </div>

      {error && <Alert variant="error"><AlertDescription>{error}</AlertDescription></Alert>}
      {!forms && !error && <p role="status" className={styles.muted}><Spinner size="sm" aria-hidden="true" /> Loading forms…</p>}
      {forms?.length === 0 && (
        <div className={styles.panel}>
          <div className={styles.panelBody}>
            <InlineEmptyState icon={FileText} title="No lead forms yet"
              description="A form lists what an agent should find out, such as a name, an email and what they need." />
          </div>
        </div>
      )}
      {forms && forms.length > 0 && (
        <div className={styles.panel}>
          <ul className={styles.list} aria-label="Lead forms">
            {forms.map((form) => (
              <li key={form.form_id} className={styles.panelBody}>
                <div className={styles.toolbar}>
                  <div>
                    <LinkButton to={`/dashboard/leads/forms/${form.form_id}`} variant="link">{form.name}</LinkButton>
                    <p className={styles.muted}>
                      {form.form_inputs.length} field{form.form_inputs.length === 1 ? "" : "s"} · version {form.version} ·{" "}
                      {form.capture_count} lead{form.capture_count === 1 ? "" : "s"}
                    </p>
                  </div>
                  {form.status === "archived" && <Pill size="sm" variant="secondary">Archived</Pill>}
                </div>
                <div className={styles.macro}>
                  <code className={styles.mono}>{macroFor(form.slug)}</code>
                  <Button type="button" variant="ghost" size="sm" aria-label={`Copy the macro for ${form.name}`}
                    onClick={() => void copyMacro(form.slug)}>
                    <Copy aria-hidden="true" />{copied === form.slug ? "Copied" : "Copy"}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
