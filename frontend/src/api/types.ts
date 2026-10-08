export type ResearchStatus = "success" | "evidence_insufficient" | "error";

export interface Verification {
  sufficient: boolean;
  supported_points: string[];
  missing_points: string[];
  weak_evidence_ids: string[];
  suggested_queries: string[];
  reason: string;
}

export interface ResearchSource {
  source_id: string;
  source_title: string;
  source_type: string;
  evidence_ids: string[];
  sections: string[];
}

export interface StageTrace {
  stage: string | null;
  agent: string | null;
  attempt: number | null;
  latency_ms: number | null;
  status: string | null;
  error_type: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  provider: string | null;
  model: string | null;
}

export interface ResearchDiagnostics {
  result_status: string;
  provider_failure: boolean;
  draft_validation_failure: boolean;
  evidence_insufficient: boolean;
  fallback_used: boolean;
  draft_repair_attempts: number;
  retrieval_repair_attempts: number | null;
  total_tokens: number | null;
  duration_ms: number | null;
  failure_stage: string | null;
  error_type: string | null;
  stage_traces: StageTrace[];
}

export interface ResearchResponse {
  run_id: string;
  status: ResearchStatus;
  session_id: string | null;
  answer: string;
  sources: ResearchSource[];
  verification: Verification | null;
  diagnostics: ResearchDiagnostics;
  error: { code: string; message: string } | null;
}

export interface ResearchRequest {
  query: string;
  session_id?: string | null;
}

export type SseEventName =
  | "run.started"
  | "task.started"
  | "task.completed"
  | "artifact.created"
  | "retrieval.completed"
  | "draft.completed"
  | "verification.completed"
  | "run.completed"
  | "run.failed";

export interface SseEnvelope<T = Record<string, unknown>> {
  event: SseEventName;
  run_id: string;
  timestamp: string;
  sequence: number;
  data: T;
}

export interface DocumentRecord {
  document_id: string;
  source_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  duplicate: boolean;
}

export interface DocumentDeleteResponse {
  document_id: string;
  source_id: string;
  status: "deleted";
  removed_chunks: number;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface SessionRun {
  runId: string;
  query: string;
  status: ResearchStatus;
  completedAt: string;
  result: ResearchResponse;
}
