import { X, FileText } from "lucide-react";
import { Button } from "../ui/button";

interface AttachmentChipProps {
  filename: string;
  size: number;
  onRemove?: () => void;
  readonly?: boolean;
}

/**
 * Displays an attachment as a compact chip with filename and size.
 * In edit mode (readonly=false), shows a remove button.
 */
export function AttachmentChip({
  filename,
  size,
  onRemove,
  readonly,
}: AttachmentChipProps) {
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  };

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        padding: "0.25rem 0.5rem",
        borderRadius: "0.5rem",
        backgroundColor: "var(--bg-tertiary, #2a2a3e)",
        border: "1px solid var(--border-subtle, #3d3d5c)",
        fontSize: "0.75rem",
        color: "var(--text-secondary, #a0a0b0)",
      }}
    >
      <FileText size={14} />
      <span
        style={{
          maxWidth: "150px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {filename}
      </span>
      <span style={{ color: "var(--text-muted, #707080)" }}>
        ({formatSize(size)})
      </span>
      {!readonly && onRemove && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onRemove}
          style={{
            padding: "2px",
            height: "1.25rem",
            width: "1.25rem",
            color: "var(--text-muted, #707080)",
          }}
          aria-label={`Remove ${filename}`}
        >
          <X size={14} />
        </Button>
      )}
    </div>
  );
}
