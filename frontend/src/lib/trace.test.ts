import { describe, expect, it } from "vitest";
import type { SseEnvelope } from "../api/types";
import { buildTaskTraces } from "./trace";

const event = (name: SseEnvelope["event"], sequence: number, data: Record<string, unknown>): SseEnvelope => ({
  event: name, run_id: "run", timestamp: `2026-01-01T00:00:0${sequence}Z`, sequence, data,
});

describe("buildTaskTraces", () => {
  it("moves tasks only from observed started to completed events", () => {
    const traces = buildTaskTraces([
      event("task.started", 1, { task_id: "task:research:evidence", agent: "ResearchAgent" }),
      event("artifact.created", 2, { task_id: "task:research:evidence", agent: "ResearchAgent", artifact_id: "a1", artifact_kind: "evidence_pool" }),
      event("task.completed", 3, { task_id: "task:research:evidence", agent: "ResearchAgent" }),
    ]);
    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({ status: "completed", agent: "ResearchAgent", artifacts: [{ id: "a1", kind: "evidence_pool" }] });
  });

  it("does not create tasks when no task event exists", () => {
    expect(buildTaskTraces([event("run.completed", 1, { status: "success" })])).toEqual([]);
  });
});
