import { Box, ChevronDown, ChevronRight, Clock3 } from "lucide-react";
import { useMemo, useState } from "react";
import type { SseEnvelope } from "../../api/types";
import { buildTaskTraces, taskLabel } from "../../lib/trace";
import { StatusBadge } from "../common/StatusBadge";

export function AgentTrace({ events, active }: { events: SseEnvelope[]; active: boolean }) {
  const tasks = useMemo(() => buildTaskTraces(events), [events]);
  const [expanded, setExpanded] = useState<string | null>(null);
  return (
    <section className="rounded-2xl border border-line bg-white shadow-panel">
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <h2 className="font-semibold text-ink">Agent execution trace</h2>
          <p className="mt-1 text-xs text-slate-500">Derived from observed runtime events</p>
        </div>
        {active && <StatusBadge status="running" label="Running" />}
      </div>
      <div className="p-4">
        {!tasks.length ? (
          <div className="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            {active ? "Waiting for the first task event…" : "No task events received yet."}
          </div>
        ) : (
          <ol className="relative space-y-2 before:absolute before:bottom-5 before:left-[18px] before:top-5 before:w-px before:bg-slate-200">
            {tasks.map((task) => {
              const open = expanded === task.taskId;
              return (
                <li key={task.taskId} className="relative">
                  <button
                    type="button"
                    onClick={() => setExpanded(open ? null : task.taskId)}
                    className="relative flex w-full items-center gap-3 rounded-xl border border-transparent bg-white p-2 text-left hover:border-line hover:bg-slate-50"
                  >
                    <span className={`z-10 flex h-9 w-9 items-center justify-center rounded-full border-4 border-white ${
                      task.status === "completed" ? "bg-emerald-100 text-emerald-700" : task.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-blue-100 text-blue-700"
                    }`}>
                      <Clock3 className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-ink">{taskLabel(task.taskId)}</span>
                      <span className="block truncate text-xs text-slate-500">{task.agent}</span>
                    </span>
                    <StatusBadge status={task.status} />
                    {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                  </button>
                  {open && (
                    <div className="ml-12 mr-2 rounded-lg border border-line bg-slate-50 p-3 text-xs text-slate-600">
                      <dl className="grid gap-2">
                        <div><dt className="font-semibold text-slate-700">Task ID</dt><dd className="mt-0.5 break-all font-mono">{task.taskId}</dd></div>
                        {task.startedAt && <div><dt className="font-semibold text-slate-700">Started</dt><dd>{new Date(task.startedAt).toLocaleTimeString()}</dd></div>}
                        {task.completedAt && <div><dt className="font-semibold text-slate-700">Completed</dt><dd>{new Date(task.completedAt).toLocaleTimeString()}</dd></div>}
                      </dl>
                      {task.artifacts.length > 0 && (
                        <div className="mt-3 border-t border-line pt-3">
                          <div className="mb-2 flex items-center gap-1.5 font-semibold text-slate-700"><Box className="h-3.5 w-3.5" /> Artifacts</div>
                          {task.artifacts.map((artifact) => <div key={artifact.id} className="break-all font-mono text-[11px]">{artifact.kind} · {artifact.id}</div>)}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </section>
  );
}
