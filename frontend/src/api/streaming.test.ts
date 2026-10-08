import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { parseSseStream, streamResearch } from "./streaming";

afterEach(() => vi.unstubAllGlobals());

function chunked(bytes: Uint8Array, cuts: number[]): ReadableStream<Uint8Array> {
  let start = 0;
  return new ReadableStream({
    start(controller) {
      for (const end of cuts) {
        controller.enqueue(bytes.slice(start, end));
        start = end;
      }
      controller.enqueue(bytes.slice(start));
      controller.close();
    },
  });
}

describe("parseSseStream", () => {
  it("handles UTF-8 boundaries, CRLF, multiple events, and id fields", async () => {
    const source = [
      "id: evt-1\r\nevent: task.started\r\ndata: {\"message\":\"研究开始\"}\r\n\r\n",
      "event: run.completed\ndata: {\"status\":\"success\"}\n\n",
    ].join("");
    const bytes = new TextEncoder().encode(source);
    const events: unknown[] = [];
    await parseSseStream(chunked(bytes, [7, 41, 42, 73]), (event) => events.push(event));
    expect(events).toEqual([
      { event: "task.started", id: "evt-1", data: { message: "研究开始" } },
      { event: "run.completed", id: undefined, data: { status: "success" } },
    ]);
  });

  it("rejects malformed event JSON", async () => {
    const bytes = new TextEncoder().encode("event: run.started\ndata: {broken}\n\n");
    await expect(parseSseStream(chunked(bytes, []), () => undefined)).rejects.toMatchObject({ code: "invalid_sse_json" });
  });

  it("handles CRLF when the carriage return and newline arrive in separate chunks", async () => {
    const source = "event: message\r\ndata: {\"ok\":true}\r\n\r\n";
    const bytes = new TextEncoder().encode(source);
    const split = source.indexOf("\r\n") + 1;
    const events: unknown[] = [];
    await parseSseStream(chunked(bytes, [split]), (event) => events.push(event));
    expect(events).toEqual([{ event: "message", id: undefined, data: { ok: true } }]);
  });

  it("treats a disconnected stream without a terminal event as failure", async () => {
    const envelope = {
      event: "run.started", run_id: "run", timestamp: "2026-01-01T00:00:00Z", sequence: 1, data: { streaming: "stage" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      `event: run.started\ndata: ${JSON.stringify(envelope)}\n\n`,
      { status: 200, headers: { "Content-Type": "text/event-stream" } },
    )));
    await expect(streamResearch({ query: "test" }, () => undefined)).rejects.toMatchObject({ code: "missing_terminal_event" });
  });
});
