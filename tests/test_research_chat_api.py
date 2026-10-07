from __future__ import annotations

import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents.events import AgentEvent, AgentEventType, CollaborationBlackboard
from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.api.routes import get_research_chat_service, router
from app.core.config import Settings
from app.core.database import Base
from app.core.security import current_user
from app.models.entities import ChatSession, UserAccount
from app.schemas.dtos import AiMessage
from app.services.research_chat import ResearchChatService
from app.services.research_memory import ResearchMemoryService
from app.services.research_pipeline import FinalResearchResult
from app.services.research_runtime import ResearchEventDrivenRuntime, ResearchRuntimeRun


def parse_sse(body: str) -> list[tuple[str, dict]]:
    parsed = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event = next(line[7:] for line in lines if line.startswith("event: "))
        data = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        parsed.append((event, data))
    return parsed


def result(query="research question") -> FinalResearchResult:
    research_task = ResearchTask(
        task_id="task-1",
        query=query,
        task_type=ResearchTaskType.FACT_LOOKUP,
        entities=["Example Agent"],
        research_questions=[query],
    )
    item = EvidenceItem(
        evidence_id="ev-1",
        source_id="source-1",
        source_title="Source",
        source_type=ResearchSourceType.DOCUMENTATION,
        content="The action result is appended to history.",
        query_used=query,
    )
    pool = EvidencePool(items=[item])
    draft = ResearchDraft(
        answer="Evidence-grounded final answer.",
        claims=[ResearchClaim(claim_id="c1", text="The result enters history.", evidence_ids=["ev-1"])],
    )
    verification = EvidenceVerificationResult(sufficient=True, supported_points=["The result enters history."])
    return FinalResearchResult(
        query=query,
        task=research_task,
        answer=draft.answer,
        evidence_pool=pool,
        draft=draft,
        verification=verification,
        sources=["Source"],
    )


class StaticRuntime:
    def run(self, query, *, user_id=None, session_id=""):
        final = result(query)
        board = CollaborationBlackboard(turn_id="turn-1", user_id=user_id, session_id=session_id)
        board = board.append_event(AgentEvent(
            type=AgentEventType.TASK_CLOSED,
            actor="ResearchAgent",
            task_id="task:research:evidence",
        ))
        return ResearchRuntimeRun(board=board, final_result=final)


class FailingRuntime:
    def run(self, query, *, user_id=None, session_id=""):
        raise RuntimeError("provider secret must not reach the client")


class FakeRedisMemory:
    def __init__(self):
        self.client = object()
        self.messages = {}
        self.summaries = {}

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


class ResearchChatApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.user = UserAccount(username="researcher", display_name="Researcher", password_hash="x")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.app = FastAPI()
        self.app.include_router(router)
        self.app.dependency_overrides[current_user] = lambda: self.user

    def client_with_runtime(self, runtime):
        service = ResearchChatService(self.db, Settings(), lambda db, settings: runtime)
        self.app.dependency_overrides[get_research_chat_service] = lambda: service
        return TestClient(self.app)

    def test_sse_status_content_type_order_and_final_answer(self):
        response = self.client_with_runtime(StaticRuntime()).post(
            "/api/research/chat/stream",
            json={"user_id": self.user.username, "session_id": None, "message": "research question"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = parse_sse(response.text)
        self.assertEqual([item[0] for item in events], ["session", "agent_event", "final", "done"])
        self.assertEqual(events[2][1]["answer"], "Evidence-grounded final answer.")
        self.assertTrue(events[2][1]["verification"]["sufficient"])
        self.assertTrue(events[0][1]["session_id"])

    def test_runtime_error_is_sanitized_sse_error(self):
        response = self.client_with_runtime(FailingRuntime()).post(
            "/api/research/chat/stream",
            json={"user_id": str(self.user.id), "session_id": None, "message": "research question"},
        )
        events = parse_sse(response.text)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item[0] for item in events], ["session", "error", "done"])
        self.assertEqual(events[1][1]["error"], "research_runtime_failed")
        self.assertNotIn("provider secret", response.text)

    def test_two_turns_reuse_session_and_task_analyzer_receives_memory_context(self):
        redis = FakeRedisMemory()
        seen_queries = []
        settings = Settings(knowledge_vector_enabled=False)

        class Analyzer:
            def analyze(self, query):
                seen_queries.append(query)
                return ResearchTask(
                    task_id=f"task-{len(seen_queries)}",
                    query=query,
                    task_type=ResearchTaskType.FACT_LOOKUP,
                    entities=["Example Agent"] if "Example Agent" in query else [],
                    research_questions=[query],
                )

        class Researcher:
            def research(self, research_task):
                return result(research_task.query).evidence_pool

        class Drafter:
            def generate(self, research_task, pool):
                return result(research_task.query).draft

        class Verifier:
            def verify(self, research_task, draft, pool):
                return EvidenceVerificationResult(sufficient=True, supported_points=[draft.claims[0].text])

        def runtime_factory(db, ignored_settings):
            memory = ResearchMemoryService(db, settings, redis)
            return ResearchEventDrivenRuntime(
                Analyzer(), Researcher(), Drafter(), Verifier(), settings, memory
            )

        service = ResearchChatService(self.db, settings, runtime_factory)
        self.app.dependency_overrides[get_research_chat_service] = lambda: service
        client = TestClient(self.app)
        first = parse_sse(client.post(
            "/api/research/chat/stream",
            json={"user_id": self.user.username, "session_id": None, "message": "Example Agent action loop"},
        ).text)
        session_id = first[0][1]["session_id"]
        second = parse_sse(client.post(
            "/api/research/chat/stream",
            json={"user_id": self.user.username, "session_id": session_id, "message": "How does it affect the next turn?"},
        ).text)
        self.assertEqual(second[0][1]["session_id"], session_id)
        self.assertIn("Example Agent action loop", seen_queries[1])
        self.assertIn("How does it affect the next turn?", seen_queries[1])
        self.assertEqual(self.db.query(ChatSession).filter(ChatSession.public_id == session_id).count(), 1)


if __name__ == "__main__":
    unittest.main()
