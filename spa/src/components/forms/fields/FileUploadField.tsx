import { Input } from "../../ui/input";
import { AttachmentChip } from "../../chat/AttachmentChip";
import type { FormInput, FormValue } from "../../../types/form";
import styles from "./FileUploadField.module.css";

interface Props {
  field: FormInput;
  value: FormValue;
  onChange: (value: FormValue) => void;
}

export function FileUploadField({ field, value, onChange }: Props) {
  const fieldAttributes = field.attr || {};

  const files = value instanceof FileList
    ? Array.from(value)
    : Array.isArray(value)
      ? value
      : [];

  return (
    <div className={styles.wrapper}>
      <Input
        id={field.name}
        name={field.name}
        type="file"
        accept={fieldAttributes.accept}
        multiple={fieldAttributes.multiple === "true"}
        onChange={(e) => onChange(e.target.files)}
      />

      {files.length > 0 && (
        <div className={styles.fileList}>
          {files.map((file) => (
            <AttachmentChip
              key={`${file.name}-${file.size}-${file.lastModified}`}
              filename={file.name}
              size={file.size}
              readonly
            />
          ))}
        </div>
      )}
    </div>
  );
}
