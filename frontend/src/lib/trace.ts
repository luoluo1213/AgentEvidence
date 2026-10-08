import type { SseEnvelope } from "../api/types";

export type TraceStatus = "pending" | "running" | "completed" | "failed";

export interface TaskTrace {
  taskId: string;
  agent: string;
  status: TraceStatus;
  startedAt?: string;
  completedAt?: string;
  artifacts: { id: string; kind: string }[];
}

export function buildTaskTraces(events: SseEnvelope[]): TaskTrace[] {
  const tasks = new Map<string, TaskTrace>();
  for (const event of events) {
    const data = event.data as Record<string, unknown>;
    const taskId = typeof data.task_id === "string" ? data.task_id : null;
    if (event.event === "task.started" && taskId) {
      tasks.set(taskId, {
        taskId,
        agent: typeof data.agent === "string" ? data.agent : "Unknown agent",
        status: "running",
        startedAt: event.timestamp,
        artifacts: tasks.get(taskId)?.artifacts ?? [],
      });
    } else if (event.event === "artifact.created" && taskId) {
      const current = tasks.get(taskId) ?? {
        taskId,
        agent: typeof data.agent === "string" ? data.agent : "Unknown agent",
        status: "running" as const,
        startedAt: event.timestamp,
        artifacts: [],
      };
      current.artifacts = [...current.artifacts, {
        id: String(data.artifact_id ?? "unknown"),
        kind: String(data.artifact_kind ?? "artifact"),
      }];
      tasks.set(taskId, current);
    } else if (event.event === "task.completed" && taskId) {
      const current = tasks.get(taskId) ?? {
        taskId,
        agent: typeof data.agent === "string" ? data.agent : "Unknown agent",
        status: "running" as const,
        artifacts: [],
      };
      tasks.set(taskId, { ...current, status: "completed", completedAt: event.timestamp });
    } else if (event.event === "run.failed") {
      for (const [id, task] of tasks) {
        if (task.status === "running") tasks.set(id, { ...task, status: "failed", completedAt: event.timestamp });
      }
    }
  }
  return [...tasks.values()];
}

export function taskLabel(taskId: string): string {
  const suffix = taskId.split(":").at(-1) ?? taskId;
  return ({
    memory_context: "Memory Context",
    analysis: "Task Analysis",
    evidence: "Evidence Retrieval",
    draft: "Draft Generation",
    verification: "Evidence Verification",
    memory_update: "Memory Update",
  } as Record<string, string>)[suffix] ?? suffix.replaceAll("_", " ");
}
