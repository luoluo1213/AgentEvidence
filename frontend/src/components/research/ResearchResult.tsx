import { Check, Clipboard, ExternalLink, FileSearch, ShieldAlert } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { DocumentRecord, ResearchResponse } from "../../api/types";
import { displaySourceName, sourceIsIncomplete } from "../../lib/format";
import { StatusBadge } from "../common/StatusBadge";

export function ResearchResult({ result, documents }: { result: ResearchResponse; documents: DocumentRecord[] }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(result.answer);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="space-y-5">
      {result.status === "evidence_insufficient" && (
        <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" />
          <div>
            <div className="font-semibold">Evidence is insufficient</div>
            <p className="mt-1 leading-6">The verifier did not approve this as a grounded answer. Missing points and suggested retrieval queries are shown below.</p>
          </div>
        </div>
      )}
      <article className="rounded-2xl border border-line bg-white shadow-panel">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-ink">Research answer</h2>
            <StatusBadge status={result.status} />
          </div>
          <button type="button" onClick={copy} className="inline-flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50">
            {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Clipboard className="h-4 w-4" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <div className="prose prose-slate max-w-none px-5 py-6 prose-headings:tracking-tight prose-a:text-blue-600 prose-pre:overflow-x-auto prose-pre:rounded-xl prose-pre:bg-slate-950 prose-code:before:content-none prose-code:after:content-none sm:px-7">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.answer || "No answer was returned."}</ReactMarkdown>
        </div>
      </article>

      <section className="rounded-2xl border border-line bg-white shadow-panel">
        <div className="border-b border-line px-5 py-4"><h2 className="font-semibold text-ink">Sources</h2></div>
        <div className="grid gap-3 p-4 sm:grid-cols-2">
          {result.sources.length ? result.sources.map((source) => (
            <div key={source.source_id} className="rounded-xl border border-line p-4">
              <div className="flex items-start gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-700"><FileSearch className="h-4 w-4" /></span>
                <div className="min-w-0">
                  <div className="font-semibold text-slate-800">{displaySourceName(source, documents)}</div>
                  <div className="mt-1 break-all font-mono text-[11px] text-slate-400">{source.source_id}</div>
                  {sourceIsIncomplete(source, documents) && <div className="mt-2 text-xs text-amber-700">Source metadata is incomplete.</div>}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <span className="rounded bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600">{source.source_type}</span>
                {source.sections.slice(0, 3).map((section) => <span key={section} className="max-w-full truncate rounded bg-blue-50 px-2 py-1 text-[11px] text-blue-700">{section}</span>)}
              </div>
              <div className="mt-3 flex items-center gap-1 text-xs text-slate-500"><ExternalLink className="h-3 w-3" /> {source.evidence_ids.length} evidence reference{source.evidence_ids.length === 1 ? "" : "s"}</div>
            </div>
          )) : <p className="col-span-full px-2 py-6 text-center text-sm text-slate-500">No sources were returned.</p>}
        </div>
      </section>

      {result.verification && (
        <section className="rounded-2xl border border-line bg-white p-5 shadow-panel">
          <h2 className="font-semibold text-ink">Verification</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{result.verification.reason || "No verifier rationale was returned."}</p>
          {result.verification.missing_points.length > 0 && <List title="Missing points" items={result.verification.missing_points} tone="amber" />}
          {result.verification.suggested_queries.length > 0 && <List title="Suggested retrieval queries" items={result.verification.suggested_queries} tone="blue" />}
        </section>
      )}
    </div>
  );
}

function List({ title, items, tone }: { title: string; items: string[]; tone: "amber" | "blue" }) {
  return (
    <div className="mt-4">
      <h3 className="text-xs font-bold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-2 space-y-2">
        {items.map((item) => <li key={item} className={`rounded-lg px-3 py-2 text-sm ${tone === "amber" ? "bg-amber-50 text-amber-900" : "bg-blue-50 text-blue-900"}`}>{item}</li>)}
      </ul>
    </div>
  );
}
