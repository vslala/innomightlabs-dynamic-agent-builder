import { useState, type FormEvent } from "react";

import type { FormInput, UploadedLeadFile } from "../api";
import { choiceOptions, choiceVariant, collectAnswers, formatSubmission, nativeInputType } from "../forms";
import type { PendingForm } from "../useChat";

/** Uploads a file into a lead form's field; the returned id becomes that field's answer. */
export type UploadLeadFile = (leadForm: string, inputName: string, file: File) => Promise<UploadedLeadFile>;

interface FormCardProps {
  pending: PendingForm;
  disabled: boolean;
  onSubmit: (content: string, display: string) => void;
  uploadLeadFile?: UploadLeadFile;
}

export function FormCard({ pending, disabled, onSubmit, uploadLeadFile }: FormCardProps) {
  const { form, submitLabel, leadForm } = pending;
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(form.form_inputs.map((input) => [input.name, input.value ?? ""]))
  );
  const [uploading, setUploading] = useState(0);
  const trackUpload = (busy: boolean) => setUploading((count) => count + (busy ? 1 : -1));
  // Only the account's own lead forms take files: the API checks each upload against the stored field
  const uploaderFor = (input: FormInput) =>
    leadForm && uploadLeadFile ? (file: File) => uploadLeadFile(leadForm, input.name, file) : undefined;

  const setValue = (name: string, value: string) => setValues((prev) => ({ ...prev, [name]: value }));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const answers = collectAnswers(form, values);
    onSubmit(formatSubmission(form, answers), `Submitted: ${form.form_name}`);
  };

  return (
    <form className="ie-form" onSubmit={submit}>
      <div className="ie-form-title">{form.form_name}</div>
      <fieldset className="ie-form-fields" disabled={disabled}>
        {form.form_inputs.map((input) => (
          <Field
            key={input.name}
            input={input}
            value={values[input.name] ?? ""}
            onChange={(value) => setValue(input.name, value)}
            upload={uploaderFor(input)}
            onUploading={trackUpload}
          />
        ))}
      </fieldset>
      <button type="submit" className="ie-button ie-button-primary" disabled={disabled || uploading > 0}>
        {submitLabel}
      </button>
    </form>
  );
}

interface FieldProps {
  input: FormInput;
  value: string;
  onChange: (value: string) => void;
  upload?: (file: File) => Promise<UploadedLeadFile>;
  onUploading: (busy: boolean) => void;
}

function Field({ input, value, onChange, upload, onUploading }: FieldProps) {
  const placeholder = input.attr?.placeholder;

  if (input.input_type === "file_upload") {
    if (!upload) return <p className="ie-form-note">{input.label}: file uploads aren't supported in this chat.</p>;
    return <FileField input={input} onChange={onChange} upload={upload} onUploading={onUploading} />;
  }

  if (input.input_type === "text_area") {
    return (
      <label className="ie-field">
        <span className="ie-field-label">{input.label}</span>
        <textarea className="ie-input" rows={3} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      </label>
    );
  }

  if (input.input_type === "select") {
    return (
      <label className="ie-field">
        <span className="ie-field-label">{input.label}</span>
        <select className="ie-input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Select…</option>
          {choiceOptions(input).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (input.input_type === "choice") {
    const options = choiceOptions(input);
    const variant = choiceVariant(input);

    if (variant === "single-checkbox") {
      const yes = options[0]?.value || "yes";
      return (
        <label className="ie-check">
          <input type="checkbox" checked={value === yes} onChange={(e) => onChange(e.target.checked ? yes : "")} />
          <span>{input.label}</span>
        </label>
      );
    }

    const selected = new Set(value.split(",").map((item) => item.trim()).filter(Boolean));
    return (
      <fieldset className="ie-choice-group">
        <legend className="ie-field-label">{input.label}</legend>
        {options.map((option) => (
          <label className="ie-check" key={option.value}>
            {variant === "checkboxes" ? (
              <input
                type="checkbox"
                checked={selected.has(option.value)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(option.value);
                  else next.delete(option.value);
                  onChange(Array.from(next).join(", "));
                }}
              />
            ) : (
              <input type="radio" name={input.name} checked={value === option.value} onChange={() => onChange(option.value)} />
            )}
            <span>{option.label}</span>
          </label>
        ))}
      </fieldset>
    );
  }

  return (
    <label className="ie-field">
      <span className="ie-field-label">{input.label}</span>
      <input
        className="ie-input"
        type={nativeInputType(input)}
        value={value}
        maxLength={input.validation?.max_length ?? undefined}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

interface FileFieldProps {
  input: FormInput;
  onChange: (value: string) => void;
  upload: (file: File) => Promise<UploadedLeadFile>;
  onUploading: (busy: boolean) => void;
}

/** Each chosen file is uploaded straight away; the field's answer is the uploads' ids, comma-separated. */
function FileField({ input, onChange, upload, onUploading }: FileFieldProps) {
  const [files, setFiles] = useState<UploadedLeadFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const maxFiles = input.validation?.max_items ?? 1;

  const keep = (next: UploadedLeadFile[]) => {
    setFiles(next);
    onChange(next.map((file) => file.file_id).join(", "));
  };

  const choose = async (chosen: File[]) => {
    setBusy(true);
    setError(null);
    onUploading(true);
    let uploaded = files;
    try {
      for (const file of chosen.slice(0, maxFiles - files.length)) {
        uploaded = [...uploaded, await upload(file)];
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The upload failed. Please try again.");
    } finally {
      keep(uploaded);
      setBusy(false);
      onUploading(false);
    }
  };

  return (
    <div className="ie-field">
      <span className="ie-field-label">{input.label}</span>
      {files.map((file) => (
        <span className="ie-file" key={file.file_id}>
          {file.filename}
          <button
            type="button"
            className="ie-file-remove"
            aria-label={`Remove ${file.filename}`}
            onClick={() => keep(files.filter((kept) => kept.file_id !== file.file_id))}
          >
            ×
          </button>
        </span>
      ))}
      {files.length < maxFiles && (
        <input
          type="file"
          className="ie-input"
          aria-label={input.label}
          accept={input.validation?.accept?.join(",")}
          multiple={maxFiles - files.length > 1}
          disabled={busy}
          onChange={(e) => {
            const chosen = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (chosen.length) void choose(chosen);
          }}
        />
      )}
      {busy && <span className="ie-form-note">Uploading…</span>}
      {error && (
        <span className="ie-form-note ie-form-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
