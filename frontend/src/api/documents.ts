import { requestJson } from "./client";
import type { DocumentDeleteResponse, DocumentRecord } from "./types";

export function listDocuments(signal?: AbortSignal): Promise<DocumentRecord[]> {
  return requestJson<DocumentRecord[]>("/documents", { signal });
}

export function getDocument(documentId: string, signal?: AbortSignal): Promise<DocumentRecord> {
  return requestJson<DocumentRecord>(`/documents/${encodeURIComponent(documentId)}`, { signal });
}

export function uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("file", file);
  return requestJson<DocumentRecord>("/documents/upload", {
    method: "POST",
    body,
    signal,
  });
}

export function deleteDocument(documentId: string, signal?: AbortSignal): Promise<DocumentDeleteResponse> {
  return requestJson<DocumentDeleteResponse>(`/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
    signal,
  });
}
