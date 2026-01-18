import { useState, useCallback } from "react";
import * as XLSX from "xlsx";
import type { Attachment } from "../types/message";
import {
  ALLOWED_EXTENSIONS,
  EXCEL_EXTENSIONS,
  MAX_FILE_SIZE,
  MAX_TOTAL_SIZE,
  MAX_FILES,
} from "../types/message";

interface UseFileAttachmentsReturn {
  attachments: Attachment[];
  error: string | null;
  addFiles: (files: FileList | File[]) => Promise<void>;
  removeAttachment: (index: number) => void;
  clearAttachments: () => void;
  totalSize: number;
}

/**
 * Hook for managing file attachments in the chat input.
 *
 * Handles file validation, reading content, and state management.
 * Validates file extensions, individual file size, and total size.
 * Converts Excel files (.xlsx, .xls) to CSV format.
 */
export function useFileAttachments(): UseFileAttachmentsReturn {
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [error, setError] = useState<string | null>(null);

  const totalSize = attachments.reduce((sum, att) => sum + att.size, 0);

  const addFiles = useCallback(
    async (files: FileList | File[]) => {
      setError(null);
      const fileArray = Array.from(files);

      // Validate count
      if (attachments.length + fileArray.length > MAX_FILES) {
        setError(`Maximum ${MAX_FILES} files allowed`);
        return;
      }

      const newAttachments: Attachment[] = [];

      for (const file of fileArray) {
        // Validate extension
        const ext = "." + file.name.split(".").pop()?.toLowerCase();
        if (!ALLOWED_EXTENSIONS.includes(ext)) {
          setError(`File type '${ext}' not supported`);
          continue;
        }

        // Validate size
        if (file.size > MAX_FILE_SIZE) {
          setError(`${file.name} exceeds 100KB limit`);
          continue;
        }

        // Check total size
        const newTotalSize =
          totalSize +
          newAttachments.reduce((s, a) => s + a.size, 0) +
          file.size;
        if (newTotalSize > MAX_TOTAL_SIZE) {
          setError("Total attachment size exceeds 250KB");
          break;
        }

        // Check for duplicate filenames (use converted name for Excel)
        const displayName = EXCEL_EXTENSIONS.includes(ext)
          ? file.name.replace(/\.xlsx?$/i, ".csv")
          : file.name;
        const isDuplicate =
          attachments.some((a) => a.filename === displayName) ||
          newAttachments.some((a) => a.filename === displayName);
        if (isDuplicate) {
          setError(`${displayName} is already attached`);
          continue;
        }

        // Read file content
        try {
          let content: string;
          let filename: string;

          if (EXCEL_EXTENSIONS.includes(ext)) {
            // Convert Excel to CSV
            content = await readExcelAsCSV(file);
            filename = file.name.replace(/\.xlsx?$/i, ".csv");
          } else {
            // Read as plain text
            content = await readFileAsText(file);
            filename = file.name;
          }

          newAttachments.push({
            filename,
            content,
            size: content.length, // Use content size for converted files
          });
        } catch (e) {
          const errorMsg = e instanceof Error ? e.message : "Unknown error";
          setError(`Failed to read ${file.name}: ${errorMsg}`);
        }
      }

      if (newAttachments.length > 0) {
        setAttachments((prev) => [...prev, ...newAttachments]);
      }
    },
    [attachments, totalSize]
  );

  const removeAttachment = useCallback((index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index));
    setError(null);
  }, []);

  const clearAttachments = useCallback(() => {
    setAttachments([]);
    setError(null);
  }, []);

  return {
    attachments,
    error,
    addFiles,
    removeAttachment,
    clearAttachments,
    totalSize,
  };
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

/**
 * Read an Excel file and convert all sheets to CSV format.
 */
function readExcelAsCSV(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = new Uint8Array(e.target?.result as ArrayBuffer);
        const workbook = XLSX.read(data, { type: "array" });

        // Convert each sheet to CSV and combine
        const csvParts: string[] = [];
        for (const sheetName of workbook.SheetNames) {
          const sheet = workbook.Sheets[sheetName];
          const csv = XLSX.utils.sheet_to_csv(sheet);
          if (workbook.SheetNames.length > 1) {
            csvParts.push(`--- Sheet: ${sheetName} ---\n${csv}`);
          } else {
            csvParts.push(csv);
          }
        }

        resolve(csvParts.join("\n\n"));
      } catch (err) {
        reject(new Error("Failed to parse Excel file"));
      }
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}
