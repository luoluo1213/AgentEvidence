import { CheckCircle2, RefreshCw, Server, ShieldCheck, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { API_BASE_URL, requestJson } from "../api/client";
import type { HealthResponse } from "../api/types";
import { PageHeader } from "../components/layout/PageHeader";

export function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = async () => {
    setChecking(true);
    try {
      setHealth(await requestJson<HealthResponse>("/health"));
      setError(null);
    } catch (caught) {
      setHealth(null);
      setError(caught instanceof Error ? caught.message : "Health check failed.");
    } finally {
      setChecking(false);
    }
  };
  useEffect(() => { void check(); }, []);

  return (
    <div>
      <PageHeader eyebrow="Workspace" title="Settings" description="Safe browser-visible configuration and service information. Provider credentials remain server-side." />
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="rounded-2xl border border-line bg-white p-5 shadow-panel">
          <div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-700"><Server className="h-5 w-5" /></span><div><h2 className="font-semibold text-ink">Backend service</h2><p className="text-xs text-slate-500">Public health metadata</p></div></div><button type="button" onClick={() => void check()} disabled={checking} className="rounded-lg border border-line p-2 text-slate-500 hover:bg-slate-50"><RefreshCw className={`h-4 w-4 ${checking ? "animate-spin" : ""}`} /></button></div>
          <dl className="mt-5 divide-y divide-line border-y border-line text-sm">
            <Row label="API base URL" value={API_BASE_URL} mono />
            <Row label="Status" value={health ? <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Online</span> : error ? <span className="inline-flex items-center gap-1.5 text-rose-700"><WifiOff className="h-4 w-4" /> Unavailable</span> : "Checking…"} />
            <Row label="Service" value={health?.service ?? "Not available"} />
            <Row label="Version" value={health?.version ?? "Not available"} />
          </dl>
          {error && <p className="mt-4 text-sm text-rose-700">{error}</p>}
        </section>

        <section className="rounded-2xl border border-line bg-white p-5 shadow-panel">
          <div className="flex items-center gap-3"><span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><ShieldCheck className="h-5 w-5" /></span><div><h2 className="font-semibold text-ink">Frontend behavior</h2><p className="text-xs text-slate-500">Actual integration capabilities</p></div></div>
          <dl className="mt-5 divide-y divide-line border-y border-line text-sm">
            <Row label="Research stream" value="POST SSE · stage-level" />
            <Row label="Run history" value="Current browser tab only" />
            <Row label="PDF client limit" value="20 MB" />
            <Row label="Persistent chat memory" value="Not available" />
            <Row label="Retrieval Repair" value="Not connected" />
          </dl>
          <p className="mt-4 text-xs leading-5 text-slate-400">No chat-provider or embedding keys are available to this application. Every VITE_ variable is considered public.</p>
        </section>
      </div>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return <div className="flex items-start justify-between gap-4 py-3"><dt className="text-slate-500">{label}</dt><dd className={`break-all text-right font-medium text-slate-800 ${mono ? "font-mono text-xs" : ""}`}>{value}</dd></div>;
}
