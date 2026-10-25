import { useCallback, useEffect, useState } from "react";
import { DOCUMENT_POLL_INTERVAL_MS, anyInFlight } from "../lib/documents";
import { conversationApiService } from "../services/conversations";
import type { KnowledgeDocument } from "../types/knowledge";
import type { MessageReference } from "../types/message";

/** A file on its way up, before the server has made it a document. */
export interface UploadingDocument {
  localId: string;
  filename: string;
}

/**
 * The composer's documents: uploaded to the conversation and not yet sent, the ones uploading, and upload, remove
 * and send.
 *
 * The server reads each document in the background; sending the message hands them to the agent as references
 * (`takeForSending`), and the list shows only those not yet sent, so a reload doesn't bring sent ones back. The list
 * is looked at again every few seconds while any is still being read.
 */
export function useConversationDocuments(conversationId: string | undefined) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [uploading, setUploading] = useState<UploadingDocument[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDocuments([]);
    if (!conversationId) return;
    let current = true;
    conversationApiService
      .listDocuments(conversationId, { unsent: true })
      .then((listed) => current && setDocuments(listed))
      .catch((err) => console.error("Error loading conversation documents:", err));
    return () => {
      current = false;
    };
  }, [conversationId]);

  const reading = anyInFlight(documents);
  useEffect(() => {
    if (!conversationId || !reading) return;
    const timer = setInterval(() => {
      conversationApiService
        .listDocuments(conversationId, { unsent: true })
        .then(setDocuments)
        .catch((err) => console.error("Error polling conversation documents:", err));
    }, DOCUMENT_POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [conversationId, reading]);

  const addDocuments = useCallback(
    (files: File[]) => {
      if (!conversationId || files.length === 0) return;
      setError(null);
      files.forEach(async (file) => {
        const localId = crypto.randomUUID();
        setUploading((current) => [...current, { localId, filename: file.name }]);
        try {
          const document = await conversationApiService.uploadDocument(conversationId, file);
          setDocuments((current) => [...current, document]);
        } catch (err) {
          // The server's refusal (type, size, rate limit) is worded to show as is
          setError(`${file.name}: ${err instanceof Error ? err.message : "Upload failed."}`);
        } finally {
          setUploading((current) => current.filter((each) => each.localId !== localId));
        }
      });
    },
    [conversationId],
  );

  const removeDocument = useCallback(
    async (document: KnowledgeDocument) => {
      if (!conversationId) return;
      setError(null);
      try {
        await conversationApiService.deleteDocument(conversationId, document.document_id);
        setDocuments((current) => current.filter((each) => each.document_id !== document.document_id));
      } catch (err) {
        setError(`Couldn't remove ${document.filename}: ${err instanceof Error ? err.message : "try again."}`);
      }
    },
    [conversationId],
  );

  /** The documents to send with the message, as references; the composer no longer shows them. */
  const takeForSending = useCallback((): MessageReference[] => {
    const references = documents.map((document) => documentReference(document));
    setDocuments([]);
    return references;
  }, [documents]);

  return { documents, uploading, error, addDocuments, removeDocument, takeForSending };
}

export function documentReference(document: KnowledgeDocument): MessageReference {
  return { kind: "document", id: document.document_id, label: document.filename };
}
