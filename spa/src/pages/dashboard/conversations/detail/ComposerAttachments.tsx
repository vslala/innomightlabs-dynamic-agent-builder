import { AttachmentChip } from "../../../../components/chat/AttachmentChip";
import { ImageAttachmentChip } from "../../../../components/chat/ImageAttachmentChip";
import { DocumentChip } from "../../../../components/chat/DocumentChip";
import type { useConversationImages } from "../../../../hooks/useConversationImages";
import type { useConversationDocuments } from "../../../../hooks/useConversationDocuments";
import { documentStatusLabel, isInFlight } from "../../../../lib/documents";
import type { Attachment } from "../../../../types/message";

interface ComposerAttachmentsProps {
  files: Attachment[];
  onRemoveFile: (index: number) => void;
  images: ReturnType<typeof useConversationImages>;
  documents: ReturnType<typeof useConversationDocuments>;
}

/** Everything that goes with the next message: text files, images (uploading as soon as they are added) and documents. */
export function ComposerAttachments({ files, onRemoveFile, images, documents }: ComposerAttachmentsProps) {
  return (
    <>
      {files.map((file, index) => (
        <AttachmentChip
          key={`${file.filename}-${index}`}
          filename={file.filename}
          size={file.size}
          onRemove={() => onRemoveFile(index)}
        />
      ))}
      {images.images.map((image) => (
        <ImageAttachmentChip
          key={image.localId}
          image={image}
          onRemove={() => images.removeImage(image.localId)}
          onRetry={() => images.retryImage(image.localId)}
        />
      ))}
      {documents.documents.map((attached) => (
        <DocumentChip
          key={attached.document_id}
          filename={attached.filename}
          label={documentStatusLabel(attached.status, attached.error)}
          state={attached.status === "failed" ? "failed" : isInFlight(attached.status) ? "busy" : "ready"}
          error={attached.error}
          onRemove={() => void documents.removeDocument(attached)}
        />
      ))}
      {documents.uploading.map((upload) => (
        <DocumentChip key={upload.localId} filename={upload.filename} label="Uploading" state="busy" />
      ))}
    </>
  );
}
