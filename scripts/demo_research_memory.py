from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.evidence_verifier import EvidenceVerifier
from app.agents.research_agent import ResearchAgent
from app.agents.research_draft_generator import ResearchDraftGenerator
from app.agents.research_task_analyzer import TaskAnalyzerAgent
from app.core.config import Settings
from app.core.database import Base
from app.models.entities import ChatSession, ResearchLongTermMemory, UserAccount
from app.schemas.dtos import AiMessage
from app.services.research_memory import ResearchMemoryService
from app.services.research_runtime import ResearchEventDrivenRuntime
from scripts.demo_research_agent import build_local_knowledge_service
from scripts.demo_research_draft import DemoEvidenceVerifierClient, DemoGroundedDraftClient
from scripts.demo_task_analyzer import DemoMockAiClient


class DemoSessionStore:
    """In-memory stand-in for Redis so the demo has no external dependency."""

    def __init__(self):
        self.client = object()
        self.messages: dict[str, list[AiMessage]] = {}
        self.summaries: dict[str, str] = {}

    def load_recent(self, session_id):
        return list(self.messages.get(session_id, []))

    def append(self, session_id, role, content):
        self.messages.setdefault(session_id, []).append(AiMessage(role=role, content=content))

    def messages_from_rows(self, rows):
        return [AiMessage(role=row.role, content=row.content) for row in rows]

    def load_summary(self, session_id):
        return self.summaries.get(session_id, "")

    def save_summary(self, session_id, summary):
        self.summaries[session_id] = summary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    settings = Settings(knowledge_vector_enabled=False)
    memory_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(memory_engine)
    memory_db = sessionmaker(bind=memory_engine)()
    user = UserAccount(username="demo-researcher", display_name="Demo Researcher", password_hash="demo")
    memory_db.add(user)
    memory_db.commit()
    memory_db.refresh(user)
    session_id = "research-memory-demo"
    memory_db.add(ChatSession(public_id=session_id, user_id=user.id, title="Research memory demo"))
    memory_db.commit()
    session_store = DemoSessionStore()
    memory = ResearchMemoryService(memory_db, settings, session_store)

    knowledge, knowledge_db = build_local_knowledge_service(settings)
    runtime = ResearchEventDrivenRuntime(
        TaskAnalyzerAgent(DemoMockAiClient()),
        ResearchAgent(
            knowledge,
            top_k=settings.research_retrieval_top_k,
            max_evidence_items=settings.research_max_evidence_items,
        ),
        ResearchDraftGenerator(DemoGroundedDraftClient()),
        EvidenceVerifier(DemoEvidenceVerifierClient()),
        settings,
        memory,
    )
    try:
        first_query = "mini-SWE-agent 如何执行 action？"
        print("=== Turn 1 ===")
        print(f"User: {first_query}")
        first = runtime.run(first_query, user_id=user.id, session_id=session_id)
        print(f"Assistant: {first.final_result.answer if first.final_result else 'No result'}")

        second_query = "那它执行完以后怎么影响下一轮？"
        print("\n=== Turn 2 ===")
        print(f"User: {second_query}")
        second = runtime.run(second_query, user_id=user.id, session_id=session_id)
        context = second.board.latest_artifact("conversation_context").payload["value"]
        print("\nMemory Context:")
        print(context.session_summary or "none")
        print("\nContextualized Query:")
        print(context.contextualized_query)
        print("\nAssistant:")
        print(second.final_result.answer if second.final_result else "No result")

        print("\n=== Memory Layers (summary) ===")
        print(f"L0 Working Memory: {len(second.board.tasks)} tasks, {len(second.board.artifacts)} artifacts, {len(second.board.events)} events")
        print(f"L1 Session Memory: {len(context.recent_messages)} recent messages; summary={'YES' if context.session_summary else 'NO'}")
        print(f"L2 Long-term Memory: {memory_db.query(ResearchLongTermMemory).count()} stable records")
        print(f"L3 Knowledge Memory: {len(second.final_result.evidence_pool.items) if second.final_result else 0} retrieved evidence items")
    finally:
        knowledge_db.close()
        memory_db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
