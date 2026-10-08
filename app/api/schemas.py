from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=20_000)
    session_id: str | None = Field(default=None, max_length=128)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be empty")
        return normalized

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


class VerificationResponse(BaseModel):
    sufficient: bool
    supported_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    weak_evidence_ids: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    reason: str = ""


class SourceResponse(BaseModel):
    source_id: str
    source_title: str
    source_type: str
    evidence_ids: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)


class StageTraceResponse(BaseModel):
    stage: str | None = None
    agent: str | None = None
    attempt: int | None = None
    latency_ms: float | None = None
    status: str | None = None
    error_type: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    provider: str | None = None
    model: str | None = None


class ResearchDiagnosticsResponse(BaseModel):
    result_status: str
    provider_failure: bool = False
    draft_validation_failure: bool = False
    evidence_insufficient: bool = False
    fallback_used: bool = False
    draft_repair_attempts: int = 0
    retrieval_repair_attempts: int | None = None
    total_tokens: int | None = None
    duration_ms: float | None = None
    failure_stage: str | None = None
    error_type: str | None = None
    stage_traces: list[StageTraceResponse] = Field(default_factory=list)


class ResearchResponse(BaseModel):
    run_id: str
    status: Literal["success", "evidence_insufficient", "error"]
    session_id: str | None = None
    answer: str = ""
    sources: list[SourceResponse] = Field(default_factory=list)
    verification: VerificationResponse | None = None
    diagnostics: ResearchDiagnosticsResponse
    error: dict[str, str] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class DocumentResponse(BaseModel):
    document_id: str
    source_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    chunk_count: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    duplicate: bool = False


class DocumentDeleteResponse(BaseModel):
    document_id: str
    source_id: str
    status: Literal["deleted"]
    removed_chunks: int


class ErrorEnvelope(BaseModel):
    error: dict[str, str]
