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
import { KB_UPLOAD_ALLOWED_EXTENSIONS, KB_UPLOAD_MAX_FILE_SIZE } from "../../../types/knowledge";
import type { ContentUploadResponse } from "../../../types/knowledge";
import type { FormSchema, FormValue } from "../../../types/form";
import styles from "./dialogs.module.css";

interface UploadContentDialogProps {
  kbId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Files went in: the totals the knowledge base has now. */
  onUploaded: (totals: ContentUploadResponse) => void;
}

function extensionOf(filename: string): string {
  const at = filename.lastIndexOf(".");
  return at >= 0 ? filename.slice(at).toLowerCase() : "";
}

function problemWith(files: File[]): string | null {
  for (const file of files) {
    const extension = extensionOf(file.name);
    if (!KB_UPLOAD_ALLOWED_EXTENSIONS.includes(extension)) return `File type '${extension || "unknown"}' is not supported.`;
    if (file.size > KB_UPLOAD_MAX_FILE_SIZE) return `${file.name} exceeds 5MB per file limit.`;
  }
  return null;
}

export function UploadContentDialog({ kbId, open, onOpenChange, onUploaded }: UploadContentDialogProps) {
  const [schema, setSchema] = useState<FormSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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

  const upload = async (data: Record<string, FormValue>) => {
    const metadata = typeof data.metadata === "string" ? data.metadata.trim() : "";
    const attachment = data.attachment;
    const files = attachment instanceof FileList ? Array.from(attachment) : Array.isArray(attachment) ? attachment : [];

    if (files.length === 0) return setError("Select at least one file to upload.");
    const problem = problemWith(files);
    if (problem) return setError(problem);

    setUploading(true);
    setError(null);
    setNotice(null);
    let uploaded = 0;
    let last: ContentUploadResponse | null = null;
    try {
      for (const file of files) {
        last = await knowledgeApiService.uploadContentFile(kbId, { file, metadata: metadata || undefined });
        uploaded += 1;
      }
      setNotice(`Uploaded ${uploaded} file${uploaded === 1 ? "" : "s"} successfully.`);
      setFormKey((key) => key + 1);
      if (last) onUploaded(last);
    } catch (err: unknown) {
      console.error("Error uploading content:", err);
      setError(err instanceof Error ? err.message : "Failed to upload content. Please try again.");
      if (last) onUploaded(last);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) {
          setError(null);
          setNotice(null);
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload content</DialogTitle>
          <DialogDescription>Upload text-based files (max 5MB per file). Multiple files upload one by one.</DialogDescription>
        </DialogHeader>
        <Stack gap="md" className={styles.fields}>
          <p className={styles.hint}>Supported: {KB_UPLOAD_ALLOWED_EXTENSIONS.join(" ")}</p>
          {error && <AlertBanner message={error} variant="error" />}
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
