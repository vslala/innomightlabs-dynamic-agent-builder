import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import {
  AlertBanner,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  InlineEmptyState,
  LoadingState,
} from "../../../components/ui";
import { Stack } from "../../../components/layout";
import { SchemaForm } from "../../../components/forms";
import { knowledgeApiService } from "../../../services/knowledge";
import { HttpError } from "../../../services/http/client";
import type { FormSchema, FormValue } from "../../../types/form";
import styles from "./dialogs.module.css";

interface UploadContentDialogProps {
  kbId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** At least one file was accepted: it's being read in the background, so the documents list should look again. */
  onUploaded: () => void;
}

/** The file types the server reads, as its upload form says: ".csv .md .pdf …". */
function acceptedTypes(schema: FormSchema | null): string {
  const accept = schema?.form_inputs.find((input) => input.input_type === "file_upload")?.attr?.accept ?? "";
  return accept.split(",").filter(Boolean).join(" ");
}

export function UploadContentDialog({ kbId, open, onOpenChange, onUploaded }: UploadContentDialogProps) {
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // One line per file the server refused, with its reason (unsupported type, too large, rate limited)
  const [refusals, setRefusals] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [formKey, setFormKey] = useState(0);

  useEffect(() => {
    if (!open || schema) return;
    setLoading(true);
    knowledgeApiService
      .getContentUploadSchema(kbId)
      .then(setSchema)
      .catch((err) => {
        console.error("Error loading content upload schema:", err);
        setError("Failed to load content upload form.");
      })
      .finally(() => setLoading(false));
  }, [open, schema, kbId]);

  const clearMessages = () => {
    setError(null);
    setRefusals([]);
    setNotice(null);
  };

  // The server decides what it can read and how big a file may be; its refusals are shown per file
  const upload = async (data: Record<string, FormValue>) => {
    const metadata = typeof data.metadata === "string" ? data.metadata.trim() : "";
    const attachment = data.attachment;
    const files = attachment instanceof FileList ? Array.from(attachment) : Array.isArray(attachment) ? attachment : [];

    clearMessages();
    if (files.length === 0) return setError("Select at least one file to upload.");

    setUploading(true);
    let accepted = 0;
    const refused: string[] = [];
    for (const [index, file] of files.entries()) {
      try {
        await knowledgeApiService.uploadContentFile(kbId, { file, metadata: metadata || undefined });
        accepted += 1;
      } catch (err: unknown) {
        console.error("Error uploading content:", err);
        refused.push(`${file.name}: ${err instanceof Error ? err.message : "Upload failed."}`);
        // Rate limited: the rest would be refused the same way
        if (err instanceof HttpError && err.status === 429) {
          const rest = files.slice(index + 1).map((skipped) => skipped.name);
          if (rest.length > 0) refused.push(`Not sent: ${rest.join(", ")}`);
          break;
        }
      }
    }
    setUploading(false);
    setRefusals(refused);
    if (accepted > 0) {
      setNotice(
        `${accepted} file${accepted === 1 ? " was" : "s were"} accepted and ${accepted === 1 ? "is" : "are"} being read in the background. ` +
          "Each shows in Documents, and its pages join the knowledge base once it's ready."
      );
      // Cleared so submitting again doesn't send the accepted files twice
      setFormKey((key) => key + 1);
      onUploaded();
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) clearMessages();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload content</DialogTitle>
          <DialogDescription>
            Upload documents (up to 25 MB each). Files are sent one by one, then read and indexed in the background.
          </DialogDescription>
        </DialogHeader>
        <Stack gap="md" className={styles.fields}>
          {acceptedTypes(schema) && <p className={styles.hint}>Supported: {acceptedTypes(schema)}</p>}
          {error && <AlertBanner message={error} variant="error" />}
          {refusals.map((refusal) => (
            <AlertBanner key={refusal} message={refusal} variant="error" />
          ))}
          {notice && <AlertBanner message={notice} variant="success" />}
          {loading ? (
            <LoadingState className={styles.loading} size="default" />
          ) : schema ? (
            <SchemaForm key={formKey} schema={schema} onSubmit={upload} submitLabel="Upload Files" isLoading={uploading} />
          ) : (
            <InlineEmptyState icon={Database} title="Upload form unavailable" description="We couldn't load the upload form. Please refresh the page." />
          )}
        </Stack>
      </DialogContent>
    </Dialog>
  );
}
