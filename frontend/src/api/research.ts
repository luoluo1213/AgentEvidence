import { requestJson } from "./client";
import type { ResearchRequest, ResearchResponse } from "./types";

export function runResearch(request: ResearchRequest, signal?: AbortSignal): Promise<ResearchResponse> {
  return requestJson<ResearchResponse>("/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
}
