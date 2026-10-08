import { AlertCircle, ArrowUp, FlaskConical, LoaderCircle, RotateCcw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { DocumentRecord, ResearchResponse, SessionRun, SseEnvelope } from "../api/types";
import { listDocuments } from "../api/documents";
import { runResearch } from "../api/research";
import { streamResearch } from "../api/streaming";
import { ApiError } from "../api/client";
import { PageHeader } from "../components/layout/PageHeader";
import { AgentTrace } from "../components/trace/AgentTrace";
import { DiagnosticsPanel } from "../components/research/DiagnosticsPanel";
import { ResearchResult } from "../components/research/ResearchResult";
import { EmptyState } from "../components/common/EmptyState";

const examples = [
  "Compare the reasoning mechanisms of ReAct and Reflexion.",
  "GeoViS 的主要方法是什么？",
  "How does attention distribute information across a sequence?",
];

type RunPhase = "idle" | "running" | "completed" | "failed" | "cancelled";

export function ResearchPage({ onRunComplete }: { onRunComplete: (run: SessionRun) => void }) {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [phase, setPhase] = useState<RunPhase>("idle");
  const [events, setEvents] = useState<SseEnvelope[]>([]);
  const [result, setResult] = useState<ResearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamFailed, setStreamFailed] = useState(false);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const controllerRef = useRef<AbortController | null>(null);
  const sessionId = useRef(`web-${crypto.randomUUID()}`);

  useEffect(() => {
    const controller = new AbortController();
    listDocuments(controller.signal).then(setDocuments).catch(() => undefined);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
    };
  }, []);

  const startStream = async (requestedQuery = query.trim()) => {
    if (!requestedQuery || phase === "running") return;
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setSubmittedQuery(requestedQuery);
    setQuery(requestedQuery);
    setPhase("running");
    setEvents([]);
    setResult(null);
    setError(null);
    setStreamFailed(false);
    try {
      const completed = await streamResearch(
        { query: requestedQuery, session_id: sessionId.current },
        (event) => setEvents((current) => [...current, event]),
        controller.signal,
      );
      if (controllerRef.current !== controller) return;
      setResult(completed);
      setPhase("completed");
      onRunComplete(toSessionRun(requestedQuery, completed));
    } catch (caught) {
      if (controllerRef.current !== controller) return;
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setPhase("cancelled");
        setError("Research request cancelled.");
      } else {
        setPhase("failed");
        setStreamFailed(true);
        setError(messageFor(caught));
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  };

  const runJsonFallback = async () => {
    if (!submittedQuery || phase === "running") return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setPhase("running");
    setError(null);
    setStreamFailed(false);
    try {
      const completed = await runResearch(
        { query: submittedQuery, session_id: sessionId.current },
        controller.signal,
      );
      if (controllerRef.current !== controller) return;
      setResult(completed);
      setPhase("completed");
      onRunComplete(toSessionRun(submittedQuery, completed));
    } catch (caught) {
      if (controllerRef.current !== controller) return;
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setPhase("cancelled");
        setError("Research request cancelled.");
      } else {
        setPhase("failed");
        setError(messageFor(caught));
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  };

  const cancel = () => controllerRef.current?.abort();

  return (
    <div>
      <PageHeader
        eyebrow="Research"
        title="Grounded answers, visible process"
        description="Ask a research question and inspect the real multi-agent execution trace, source evidence, verification result, and Harness diagnostics."
      />

      <section className="mb-6 rounded-2xl border border-line bg-white p-4 shadow-panel sm:p-5">
        <label htmlFor="research-query" className="mb-2 block text-sm font-semibold text-slate-700">Research question</label>
        <div className="relative">
          <textarea
            id="research-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                event.preventDefault();
                void startStream();
              }
            }}
            disabled={phase === "running"}
            rows={4}
            placeholder="Ask about a method, mechanism, comparison, or implementation…"
            className="w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 pr-14 text-[15px] leading-6 text-ink outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100 disabled:bg-slate-50"
          />
          {phase === "running" ? (
            <button type="button" onClick={cancel} aria-label="Cancel research" className="absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-lg bg-slate-800 text-white hover:bg-slate-700">
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button type="button" onClick={() => void startStream()} disabled={!query.trim()} aria-label="Start research" className="absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300">
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-medium text-slate-400">Try:</span>
          {examples.map((example) => (
            <button key={example} type="button" disabled={phase === "running"} onClick={() => setQuery(example)} className="max-w-full truncate rounded-full border border-line bg-slate-50 px-3 py-1.5 text-xs text-slate-600 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700">
              {example}
            </button>
          ))}
          <span className="ml-auto hidden text-xs text-slate-400 sm:block">Ctrl/⌘ + Enter to run</span>
        </div>
      </section>

      {error && (
        <div role="alert" className="mb-6 flex flex-col gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900 sm:flex-row sm:items-center">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span className="flex-1">{error}</span>
          <div className="flex gap-2">
            {streamFailed && <button type="button" onClick={() => void startStream(submittedQuery)} className="inline-flex items-center gap-1.5 rounded-lg border border-rose-300 px-3 py-2 text-xs font-semibold hover:bg-rose-100"><RotateCcw className="h-3.5 w-3.5" /> Retry stream</button>}
            {streamFailed && <button type="button" onClick={() => void runJsonFallback()} className="rounded-lg bg-rose-700 px-3 py-2 text-xs font-semibold text-white hover:bg-rose-800">Use standard request</button>}
          </div>
        </div>
      )}

      {phase === "idle" ? (
        <EmptyState icon={FlaskConical} title="Start a grounded research run" body="The answer area, source citations, agent trace, and verification diagnostics will appear here. No demo result is preloaded." />
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
          <div className="min-w-0 space-y-5">
            {phase === "running" && !result && (
              <div className="flex min-h-48 items-center justify-center rounded-2xl border border-line bg-white shadow-panel">
                <div className="text-center"><LoaderCircle className="mx-auto h-7 w-7 animate-spin text-blue-600" /><p className="mt-3 text-sm font-medium text-slate-700">Research runtime is working…</p><p className="mt-1 text-xs text-slate-400">Stage events appear when the synchronous backend exposes them.</p></div>
              </div>
            )}
            {result && <ResearchResult result={result} documents={documents} />}
          </div>
          <aside className="space-y-5 xl:sticky xl:top-6">
            <AgentTrace events={events} active={phase === "running"} />
            {result && <DiagnosticsPanel diagnostics={result.diagnostics} />}
          </aside>
        </div>
      )}
    </div>
  );
}

function messageFor(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : "Research request failed.";
}

function toSessionRun(query: string, result: ResearchResponse): SessionRun {
  return { runId: result.run_id, query, status: result.status, completedAt: new Date().toISOString(), result };
}
