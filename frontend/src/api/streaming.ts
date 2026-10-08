import { API_BASE_URL, ApiError, responseError } from "./client";
import type { ResearchRequest, ResearchResponse, SseEnvelope, SseEventName } from "./types";

export interface ParsedSseEvent {
  event: string;
  data: unknown;
  id?: string;
}

export async function parseSseStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: ParsedSseEvent) => void,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");
      if (done) buffer = buffer.replace(/\r/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (block.trim()) onEvent(parseEventBlock(block));
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) onEvent(parseEventBlock(buffer));
  } finally {
    reader.releaseLock();
  }
}

export async function streamResearch(
  request: ResearchRequest,
  onEvent: (event: SseEnvelope) => void,
  signal?: AbortSignal,
): Promise<ResearchResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/research/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the research stream.", null, "network_error");
  }
  if (!response.ok) throw await responseError(response);
  if (!response.headers.get("content-type")?.startsWith("text/event-stream")) {
    throw new ApiError("The backend did not return an SSE stream.", response.status, "invalid_content_type");
  }
  if (!response.body) throw new ApiError("The browser did not expose the response stream.", null, "missing_stream");

  let finalResult: ResearchResponse | null = null;
  let terminalFailure: ApiError | null = null;
  await parseSseStream(response.body, (parsed) => {
    if (!isEnvelope(parsed.data)) {
      throw new ApiError("The backend returned an invalid SSE envelope.", null, "invalid_sse");
    }
    const envelope = parsed.data as SseEnvelope;
    onEvent(envelope);
    if (envelope.event === "run.completed") {
      finalResult = envelope.data as unknown as ResearchResponse;
    } else if (envelope.event === "run.failed") {
      const data = envelope.data as Record<string, unknown>;
      terminalFailure = new ApiError(
        typeof data.message === "string" ? data.message : "The research run failed.",
        null,
        typeof data.code === "string" ? data.code : "run_failed",
      );
    }
  });
  if (terminalFailure) throw terminalFailure;
  if (!finalResult) throw new ApiError("The stream ended without a terminal result.", null, "missing_terminal_event");
  return finalResult;
}

function parseEventBlock(block: string): ParsedSseEvent {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator >= 0 ? line.slice(0, separator) : line;
    let value = separator >= 0 ? line.slice(separator + 1) : "";
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (!data.length) throw new ApiError("SSE event did not contain data.", null, "invalid_sse");
  try {
    return { event, data: JSON.parse(data.join("\n")), id };
  } catch {
    throw new ApiError("SSE event contained invalid JSON.", null, "invalid_sse_json");
  }
}

function isEnvelope(value: unknown): value is SseEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const item = value as Record<string, unknown>;
  return typeof item.event === "string"
    && typeof item.run_id === "string"
    && typeof item.timestamp === "string"
    && typeof item.sequence === "number"
    && typeof item.data === "object"
    && item.data !== null
    && isEventName(item.event);
}

function isEventName(value: string): value is SseEventName {
  return [
    "run.started", "task.started", "task.completed", "artifact.created",
    "retrieval.completed", "draft.completed", "verification.completed",
    "run.completed", "run.failed",
  ].includes(value);
}
