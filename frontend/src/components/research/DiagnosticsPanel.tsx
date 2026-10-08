import type { ResearchDiagnostics } from "../../api/types";
import { StatusBadge } from "../common/StatusBadge";

const unavailable = "Not available";

export function DiagnosticsPanel({ diagnostics }: { diagnostics: ResearchDiagnostics }) {
  const entries = [
    ["Result status", diagnostics.result_status],
    ["Provider failure", yesNo(diagnostics.provider_failure)],
    ["Draft validation failure", yesNo(diagnostics.draft_validation_failure)],
    ["Evidence insufficient", yesNo(diagnostics.evidence_insufficient)],
    ["Fallback used", yesNo(diagnostics.fallback_used)],
    ["Draft repair attempts", diagnostics.draft_repair_attempts],
    ["Retrieval repair attempts", diagnostics.retrieval_repair_attempts ?? unavailable],
    ["Total tokens", diagnostics.total_tokens ?? unavailable],
    ["Duration", diagnostics.duration_ms == null ? unavailable : `${diagnostics.duration_ms.toLocaleString()} ms`],
  ];
  return (
    <section className="rounded-2xl border border-line bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <h2 className="font-semibold text-ink">Run diagnostics</h2>
          <p className="mt-1 text-xs text-slate-500">Safe Harness instrumentation</p>
        </div>
        <StatusBadge status={diagnostics.result_status} />
      </div>
      <dl className="grid grid-cols-1 gap-x-6 px-5 py-2 sm:grid-cols-2">
        {entries.map(([label, value]) => (
          <div key={String(label)} className="flex items-center justify-between border-b border-slate-100 py-3 text-sm">
            <dt className="text-slate-500">{label}</dt>
            <dd className="ml-3 text-right font-medium text-slate-800">{String(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="px-5 pb-5 pt-3 text-xs leading-5 text-slate-400">
        Retrieval Repair is not connected to the current runtime; unavailable values are not treated as zero.
      </div>
    </section>
  );
}

function yesNo(value: boolean) {
  return value ? "Yes" : "No";
}
