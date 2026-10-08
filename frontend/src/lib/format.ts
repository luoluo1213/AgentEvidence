import type { DocumentRecord, ResearchSource } from "../api/types";

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function displaySourceName(source: ResearchSource, documents: DocumentRecord[]): string {
  const document = documents.find((item) => item.source_id === source.source_id);
  if (document) return document.filename;
  const title = source.source_title?.trim();
  if (title && title.toLowerCase() !== "raw" && title !== source.source_id) return title;
  return source.source_id;
}

export function sourceIsIncomplete(source: ResearchSource, documents: DocumentRecord[]): boolean {
  return !documents.some((item) => item.source_id === source.source_id)
    && (!source.source_title || source.source_title === source.source_id || source.source_title.toLowerCase() === "raw");
}
