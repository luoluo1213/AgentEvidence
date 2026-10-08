import { AlertCircle, FileText, LoaderCircle, RefreshCw, Search, Trash2, UploadCloud, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { deleteDocument, getDocument, listDocuments, uploadDocument } from "../api/documents";
import { ApiError } from "../api/client";
import type { DocumentRecord } from "../api/types";
import { EmptyState } from "../components/common/EmptyState";
import { StatusBadge } from "../components/common/StatusBadge";
import { PageHeader } from "../components/layout/PageHeader";
import { formatBytes, formatDate } from "../lib/format";

const CLIENT_MAX_BYTES = 20 * 1024 * 1024;

export function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<DocumentRecord | null>(null);
  const [pendingDelete, setPendingDelete] = useState<DocumentRecord | null>(null);
  const [deleting, setDeleting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      setDocuments(await listDocuments(signal));
      setError(null);
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) setError(messageFor(caught));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const upload = async (file: File | undefined) => {
    if (!file || uploading) return;
    setNotice(null);
    const validation = validatePdf(file);
    if (validation) {
      setError(validation);
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const document = await uploadDocument(file);
      setNotice(document.duplicate ? "This PDF was already indexed; the existing document is shown." : `${document.filename} was uploaded and indexed.`);
      await refresh();
      setSelected(document);
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const openDetails = async (documentId: string) => {
    try {
      setSelected(await getDocument(documentId));
      setError(null);
    } catch (caught) {
      setError(messageFor(caught));
    }
  };

  const confirmDelete = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      const removed = await deleteDocument(pendingDelete.document_id);
      setNotice(`Document removed with ${removed.removed_chunks} indexed chunk${removed.removed_chunks === 1 ? "" : "s"}.`);
      if (selected?.document_id === pendingDelete.document_id) setSelected(null);
      setPendingDelete(null);
      await refresh();
    } catch (caught) {
      setError(messageFor(caught));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Knowledge base"
        title="Document library"
        description="Upload PDFs into the existing PyMuPDF and hybrid retrieval pipeline. Only API-managed documents appear here."
        actions={<button type="button" onClick={() => void refresh()} disabled={loading} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh</button>}
      />

      {error && <div role="alert" className="mb-4 flex items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"><AlertCircle className="h-5 w-5 shrink-0" />{error}</div>}
      {notice && <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</div>}

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files[0]); }}
        disabled={uploading}
        className={`mb-6 flex w-full items-center justify-center rounded-2xl border-2 border-dashed px-6 py-9 text-center transition ${dragging ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white hover:border-blue-400 hover:bg-blue-50/40"}`}
      >
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(event) => void upload(event.target.files?.[0])} />
        <div>
          <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
            {uploading ? <LoaderCircle className="h-5 w-5 animate-spin" /> : <UploadCloud className="h-5 w-5" />}
          </span>
          <div className="mt-3 text-sm font-semibold text-ink">{uploading ? "Uploading and indexing…" : "Drop a PDF here or click to browse"}</div>
          <div className="mt-1 text-xs text-slate-500">PDF only · client limit 20 MB · server validation is authoritative</div>
        </div>
      </button>

      {loading && !documents.length ? (
        <div className="py-16 text-center text-sm text-slate-500"><LoaderCircle className="mx-auto mb-3 h-6 w-6 animate-spin text-blue-600" />Loading documents…</div>
      ) : documents.length === 0 ? (
        <EmptyState icon={FileText} title="No managed documents" body="Upload a PDF to create a source with page-level provenance. Fixed corpus papers remain searchable but are not listed here." />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-white shadow-panel">
          <div className="hidden grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_120px_150px_90px] gap-4 border-b border-line bg-slate-50 px-5 py-3 text-xs font-bold uppercase tracking-wide text-slate-400 md:grid">
            <span>Document</span><span>Document ID</span><span>Status</span><span>Uploaded</span><span className="text-right">Actions</span>
          </div>
          <div className="divide-y divide-line">
            {documents.map((document) => (
              <div key={document.document_id} className="grid gap-3 px-4 py-4 md:grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_120px_150px_90px] md:items-center md:px-5">
                <button type="button" onClick={() => void openDetails(document.document_id)} className="flex min-w-0 items-center gap-3 text-left">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-rose-50 text-rose-600"><FileText className="h-5 w-5" /></span>
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-800">{document.filename}</span><span className="mt-0.5 block text-xs text-slate-400">{formatBytes(document.size_bytes)} · {document.chunk_count} chunks</span></span>
                </button>
                <span className="truncate font-mono text-xs text-slate-500" title={document.document_id}>{document.document_id}</span>
                <span><StatusBadge status={document.status} /></span>
                <span className="text-xs text-slate-500">{formatDate(document.created_at)}</span>
                <span className="flex justify-end gap-1">
                  <button type="button" onClick={() => void openDetails(document.document_id)} aria-label={`View ${document.filename}`} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-blue-700"><Search className="h-4 w-4" /></button>
                  <button type="button" onClick={() => setPendingDelete(document)} aria-label={`Delete ${document.filename}`} className="rounded-lg p-2 text-slate-500 hover:bg-rose-50 hover:text-rose-700"><Trash2 className="h-4 w-4" /></button>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {selected && <DocumentDetails document={selected} onClose={() => setSelected(null)} />}
      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/30 p-4" role="dialog" aria-modal="true" aria-label="Confirm document deletion">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-rose-50 text-rose-700"><Trash2 className="h-5 w-5" /></div>
            <h2 className="mt-4 text-lg font-bold text-ink">Delete this document?</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">The backend will remove <strong>{pendingDelete.filename}</strong>, its SQLite chunks, and its Chroma vectors. Success is not assumed until the API confirms it.</p>
            {error && <div role="alert" className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</div>}
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" disabled={deleting} onClick={() => setPendingDelete(null)} className="rounded-lg border border-line px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50">Cancel</button>
              <button type="button" disabled={deleting} onClick={() => void confirmDelete()} className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:opacity-60">{deleting && <LoaderCircle className="h-4 w-4 animate-spin" />} Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function DocumentDetails({ document, onClose }: { document: DocumentRecord; onClose: () => void }) {
  const fields = [
    ["Document ID", document.document_id], ["Source ID", document.source_id],
    ["Content type", document.content_type], ["File size", formatBytes(document.size_bytes)],
    ["Indexed chunks", document.chunk_count], ["Created", formatDate(document.created_at)],
    ["Updated", formatDate(document.updated_at)],
  ];
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/25" role="dialog" aria-modal="true" aria-label="Document details">
      <div className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between"><div><div className="text-xs font-bold uppercase tracking-wide text-blue-600">Document details</div><h2 className="mt-2 break-words text-xl font-bold text-ink">{document.filename}</h2></div><button type="button" onClick={onClose} aria-label="Close document details" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"><X className="h-5 w-5" /></button></div>
        <div className="mt-5"><StatusBadge status={document.status} /></div>
        <dl className="mt-6 divide-y divide-line border-y border-line">
          {fields.map(([label, value]) => <div key={String(label)} className="py-3"><dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</dt><dd className="mt-1 break-all text-sm text-slate-700">{String(value)}</dd></div>)}
        </dl>
        {document.error && <div className="mt-5 rounded-lg bg-rose-50 p-4 text-sm text-rose-800">{document.error}</div>}
        <p className="mt-5 text-xs leading-5 text-slate-400">Page count is not displayed because the current API does not provide it.</p>
      </div>
    </div>
  );
}

export function validatePdf(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "Only PDF files can be uploaded.";
  if (file.type && file.type !== "application/pdf") return "The selected file does not have a PDF content type.";
  if (file.size > CLIENT_MAX_BYTES) return "The selected PDF exceeds the 20 MB client limit.";
  if (file.size === 0) return "The selected PDF is empty.";
  return null;
}

function messageFor(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : "Document request failed.";
}
