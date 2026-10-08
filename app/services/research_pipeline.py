from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.agents.research_draft_generator import ResearchDraft
from app.agents.research_types import EvidencePool, EvidenceVerificationResult, ResearchTask

INSUFFICIENT_EVIDENCE_ANSWER = (
    "当前证据不足，无法基于现有证据可靠生成最终回答。"
)

class TaskAnalyzer(Protocol):
    def analyze(self, query: str) -> ResearchTask:
        ...


class EvidenceResearcher(Protocol):
    def research(self, task: ResearchTask, retrieval_round: int = 1) -> EvidencePool:
        ...


class DraftGenerator(Protocol):
    def generate(self, task: ResearchTask, evidence_pool: EvidencePool) -> ResearchDraft:
        ...


class DraftVerifier(Protocol):
    def verify(
        self,
        task: ResearchTask,
        draft: ResearchDraft,
        evidence_pool: EvidencePool,
    ) -> EvidenceVerificationResult:
        ...


class FinalResearchResult(BaseModel):
    query: str
    task: ResearchTask
    answer: str
    evidence_pool: EvidencePool
    draft: ResearchDraft
    verification: EvidenceVerificationResult
    sources: list[str]


class ResearchPipeline:
    def __init__(
        self,
        task_analyzer: TaskAnalyzer,
        research_agent: EvidenceResearcher,
        draft_generator: DraftGenerator,
        evidence_verifier: DraftVerifier,
    ):
        self.task_analyzer = task_analyzer
        self.research_agent = research_agent
        self.draft_generator = draft_generator
        self.evidence_verifier = evidence_verifier

    def run(self, query: str) -> FinalResearchResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty")

        task = self.task_analyzer.analyze(normalized_query)
        evidence_pool = self.research_agent.research(task)
        draft = self.draft_generator.generate(task, evidence_pool)
        verification = self.evidence_verifier.verify(task, draft, evidence_pool)
        return build_final_research_result(normalized_query, task, evidence_pool, draft, verification)


def build_final_research_result(
    query: str,
    task: ResearchTask,
    evidence_pool: EvidencePool,
    draft: ResearchDraft,
    verification: EvidenceVerificationResult,
) -> FinalResearchResult:

    answer = (
    draft.answer
    if verification.sufficient
    else INSUFFICIENT_EVIDENCE_ANSWER
    )

    return FinalResearchResult(
        query=query,
        task=task,
        answer=answer,
        evidence_pool=evidence_pool,
        draft=draft,
        verification=verification,
        sources=_source_labels(evidence_pool, draft),
    )


GENERIC_SOURCE_TITLES = {"raw", "document", "content", "untitled"}


def _source_labels(evidence_pool: EvidencePool, draft: ResearchDraft) -> list[str]:
    evidence_by_id = {item.evidence_id: item for item in evidence_pool.items}
    cited_items = [
        evidence_by_id[evidence_id]
        for claim in draft.claims
        for evidence_id in claim.evidence_ids
        if evidence_id in evidence_by_id
    ]
    labels: list[str] = []
    for item in [*cited_items, *evidence_pool.items]:
        title = str(item.metadata.get("source_title") or item.source_title or item.source_id).strip()
        if title.lower() in GENERIC_SOURCE_TITLES:
            title = str(item.source_id).strip()
        if title.startswith("research:"):
            title = title.removeprefix("research:").replace("_", "-")
        if ":" in title:
            title = title.split(":", 1)[0]
        if title.lower() in GENERIC_SOURCE_TITLES:
            continue
        if title and title not in labels:
            labels.append(title)
    return labels
