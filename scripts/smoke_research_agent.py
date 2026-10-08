from app.agents.research_agent import ResearchAgent
from app.agents.research_types import (
    ResearchTask,
    ResearchTaskType,
    ResearchSourceType,
)
from app.core.config import Settings
from app.core.database import SessionLocal
from app.services.knowledge import KnowledgeService


settings = Settings()
db = SessionLocal()

try:
    knowledge = KnowledgeService(db, settings)

    agent = ResearchAgent(
        knowledge,
        top_k=settings.research_retrieval_top_k,
        max_evidence_items=settings.research_max_evidence_items,
    )

    task = ResearchTask(
        task_id="smoke-research-agent",
        query="How does ReAct use reasoning and environmental observations?",
        task_type=ResearchTaskType.FACT_LOOKUP,
        entities=["ReAct"],
        research_questions=[
            "How does ReAct use reasoning and environmental observations?"
        ],
        expected_source_types=[ResearchSourceType.PAPER],
        requires_comparison=False,
        requires_multiple_sources=False,
    )

    pool = agent.research(task)

    print("\n=== EvidencePool ===")
    print("items =", len(pool.items))

    for item in pool.items:
        print(
            "\n",
            item.evidence_id,
            item.source_id,
            item.score,
        )
        print(item.content[:300])

finally:
    db.close()