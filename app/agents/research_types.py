from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ResearchTaskType(str, Enum):
    FACT_LOOKUP = "FACT_LOOKUP"
    CROSS_DOCUMENT_COMPARISON = "CROSS_DOCUMENT_COMPARISON"
    MULTI_HOP_RESEARCH = "MULTI_HOP_RESEARCH"
    PAPER_REPO_ANALYSIS = "PAPER_REPO_ANALYSIS"
    GENERAL_RESEARCH = "GENERAL_RESEARCH"


class ResearchSourceType(str, Enum):
    PAPER = "paper"
    REPOSITORY = "repository"
    DOCUMENTATION = "documentation"
    BENCHMARK = "benchmark"
    OTHER = "other"


class ResearchTask(BaseModel):
    task_id: str
    query: str
    task_type: ResearchTaskType
    entities: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    expected_source_types: list[ResearchSourceType] = Field(default_factory=list)
    requires_comparison: bool = False
    requires_multiple_sources: bool = False


class EvidenceItem(BaseModel):
    evidence_id: str
    source_id: str
    source_title: str
    source_type: ResearchSourceType
    section: str | None = None
    content: str
    canonical_content: str | None = None
    display_content: str | None = None
    translated_content: str | None = None
    score: float | None = None
    query_used: str
    retrieval_round: int = 1
    chunk_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidencePool(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        if any(existing.evidence_id == item.evidence_id for existing in self.items):
            return
        self.items.append(item)

    def extend(self, items: list[EvidenceItem]) -> None:
        for item in items:
            self.add(item)

    def source_ids(self) -> list[str]:
        return list(dict.fromkeys(item.source_id for item in self.items))

    def for_round(self, round_number: int) -> list[EvidenceItem]:
        return [item for item in self.items if item.retrieval_round == round_number]

    def __len__(self) -> int:
        return len(self.items)


class EvidenceVerificationResult(BaseModel):
    sufficient: bool
    supported_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    weak_evidence_ids: list[str] = Field(default_factory=list)
    suggested_queries: list[str] = Field(default_factory=list)
    reason: str = ""


class ResearchRunMetrics(BaseModel):
    retrieval_rounds: int = 0
    retrieved_items: int = 0
    unique_sources: int = 0
    verifier_triggered: bool = False
    retrieval_repair_triggered: bool = False
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
