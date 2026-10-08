import { Clock3, History } from "lucide-react";
import type { SessionRun } from "../api/types";
import { EmptyState } from "../components/common/EmptyState";
import { StatusBadge } from "../components/common/StatusBadge";
import { PageHeader } from "../components/layout/PageHeader";
import { formatDate } from "../lib/format";

export function RunsPage({ runs }: { runs: SessionRun[] }) {
  return (
    <div>
      <PageHeader eyebrow="Session activity" title="Runs" description="Completed research requests from this browser tab only. These entries are not backend-persisted history and disappear after refresh." />
      <div className="mb-5 flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
        <Clock3 className="h-4 w-4 shrink-0" /> Temporary session history · {runs.length} run{runs.length === 1 ? "" : "s"}
      </div>
      {!runs.length ? <EmptyState icon={History} title="No completed runs in this tab" body="Start a research query. Its terminal result will be listed here without implying persistent Memory." /> : (
        <div className="space-y-3">
          {runs.map((run) => (
            <article key={run.runId} className="rounded-2xl border border-line bg-white p-5 shadow-panel">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0"><h2 className="font-semibold leading-6 text-ink">{run.query}</h2><div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400"><span className="font-mono">{run.runId}</span><span>{formatDate(run.completedAt)}</span></div></div>
                <StatusBadge status={run.status} />
              </div>
              <p className="mt-4 line-clamp-3 text-sm leading-6 text-slate-600">{run.result.answer}</p>
              <div className="mt-4 flex gap-4 border-t border-line pt-3 text-xs text-slate-500"><span>{run.result.sources.length} sources</span><span>Verifier: {run.result.verification?.sufficient ? "sufficient" : "not sufficient"}</span></div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
