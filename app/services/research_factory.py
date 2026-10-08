from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings, settings_for_research_llm
from app.research_harness.harness import HarnessEvidenceVerifier, ResearchHarness
from app.services.ai import AiClient
from app.services.knowledge import KnowledgeService
from app.services.research_runtime import ResearchEventDrivenRuntime


@dataclass(frozen=True)
class ResearchRuntimeBundle:
    runtime: ResearchEventDrivenRuntime
    harness: ResearchHarness


def build_research_runtime(
    db: Session,
    settings: Settings,
    *,
    run_id: str,
) -> ResearchRuntimeBundle:
    """Compose one isolated production runtime for one API execution."""

    client = AiClient(settings_for_research_llm(settings))
    harness = ResearchHarness.from_settings(settings, run_id=run_id)
    harness.begin_case(run_id)
    knowledge = KnowledgeService(db, settings)

    analyzer = TaskAnalyzerAgent(
        harness.wrap_client(client, stage="analysis", agent="TaskAnalyzer")
    )
    researcher = ResearchAgent(
        knowledge,
        top_k=settings.research_retrieval_top_k,
        max_evidence_items=settings.research_max_evidence_items,
    )
    draft_generator = harness.wrap_draft_generator(
        ResearchDraftGenerator(
            harness.wrap_client(client, stage="draft", agent="DraftAgent")
        )
    )
    verifier = HarnessEvidenceVerifier(
        EvidenceVerifier(
            harness.wrap_client(client, stage="verification", agent="EvidenceVerifier")
        ),
        harness,
    )
    runtime = ResearchEventDrivenRuntime(
        analyzer,
        researcher,
        draft_generator,
        verifier,
        settings,
    )
    return ResearchRuntimeBundle(runtime=runtime, harness=harness)
