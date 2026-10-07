from __future__ import annotations

import unittest
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.event_driven_runtime import EventDrivenAgentRuntimeService
from app.agents.research_draft_generator import ResearchClaim, ResearchDraft
from app.agents.research_types import (
    EvidenceItem,
    EvidencePool,
    EvidenceVerificationResult,
    ResearchSourceType,
    ResearchTask,
    ResearchTaskType,
)
from app.core.database import Base
from app.models.entities import ChatMessage, ChatSession, ResearchLongTermMemory, UserAccount
from app.schemas.dtos import AiMessage
from app.services.research_memory import ResearchMemoryService
from app.services.research_pipeline import FinalResearchResult
from app.services.research_runtime import ResearchEventDrivenRuntime


def settings():
    return SimpleNamespace(
        redis_memory_max_messages=20,
        memory_summary_max_chars=500,
        agent_max_rounds=10,
        agent_max_claims_per_round=4,
        agent_max_claims_per_agent=8,
        agent_final_acceptance_min_confidence=0.6,
    )


class FakeRedisMemory:
    def __init__(self, available=True):
        self.client = object() if available else None
        self.messages = {}
        self.summaries = {}

    def load_recent(self, session_id):
        return list(self.messages.get(session_id, [])) if self.client is not None else []

    def append(self, session_id, role, content):
        if self.client is not None:
            self.messages.setdefault(session_id, []).append(AiMessage(role=role, content=content))

    def messages_from_rows(self, rows):
        return [AiMessage(role=row.role, content=row.content) for row in rows]

    def load_summary(self, session_id):
        return self.summaries.get(session_id, "") if self.client is not None else ""

    def save_summary(self, session_id, summary):
        if self.client is not None:
            self.summaries[session_id] = summary


def task(query="How does the loop work?", entities=None):
    return ResearchTask(
        task_id="task-1",
        query=query,
        task_type=ResearchTaskType.GENERAL_RESEARCH,
        entities=entities or [],
        research_questions=[query],
    )


def final_result(research_task=None):
    research_task = research_task or task(entities=["Example Agent"])
    item = EvidenceItem(
        evidence_id="ev-1",
        source_id="source-1",
        source_title="Source",
        source_type=ResearchSourceType.DOCUMENTATION,
        content="The observation is appended to history.",
        query_used=research_task.query,
    )
    pool = EvidencePool(items=[item])
    draft = ResearchDraft(
        answer="The execution observation is appended to history and informs the next turn.",
        claims=[ResearchClaim(claim_id="c1", text="Observation enters history.", evidence_ids=["ev-1"])],
    )
    verification = EvidenceVerificationResult(sufficient=True, supported_points=["Observation enters history."])
    return FinalResearchResult(
        query=research_task.query,
        task=research_task,
        answer=draft.answer,
        evidence_pool=pool,
        draft=draft,
        verification=verification,
        sources=["Source"],
    )


class MemoryTestBase(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        user = UserAccount(username="researcher", display_name="Researcher", password_hash="x")
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        self.user = user
        self.sessions = {}
        for public_id in ("session-a", "session-b"):
            session = ChatSession(public_id=public_id, user_id=user.id, title=public_id)
            self.db.add(session)
            self.sessions[public_id] = session
        self.db.commit()


class ResearchMemoryServiceTests(MemoryTestBase):
    def test_same_session_follow_up_resolution(self):
        redis = FakeRedisMemory()
        redis.messages["session-a"] = [
            AiMessage(role="user", content="Example Agent 如何执行 action？"),
            AiMessage(role="assistant", content="它执行命令并记录 observation。"),
        ]
        service = ResearchMemoryService(self.db, settings(), redis)
        context = service.build_context(self.user.id, "session-a", "那它执行完以后怎么影响下一轮？")
        self.assertIn("Example Agent", context.contextualized_query)
        self.assertIn("那它执行完以后", context.contextualized_query)

    def test_session_isolation(self):
        redis = FakeRedisMemory()
        redis.messages["session-a"] = [AiMessage(role="user", content="Private project A")]
        service = ResearchMemoryService(self.db, settings(), redis)
        context = service.build_context(self.user.id, "session-b", "continue")
        self.assertNotIn("Private project A", context.contextualized_query)

    def test_redis_failure_falls_back_to_chat_messages(self):
        self.db.add(ChatMessage(
            user_id=self.user.id,
            session_id=self.sessions["session-a"].id,
            role="user",
            content="Database-backed research context",
        ))
        self.db.commit()
        service = ResearchMemoryService(self.db, settings(), FakeRedisMemory(available=False))
        context = service.build_context(self.user.id, "session-a", "follow up")
        self.assertIn("Database-backed research context", context.contextualized_query)

    def test_long_term_memory_persistence_and_cross_session_retrieval(self):
        service = ResearchMemoryService(self.db, settings(), FakeRedisMemory())
        result = final_result(task("Study Example Agent loop", ["Example Agent", "Agent loop"]))
        service.update(self.user.id, "session-a", "turn-a", result.query, result)
        context = service.build_context(self.user.id, "session-b", "Continue our previous analysis")
        self.assertIn("Example Agent", context.contextualized_query)
        self.assertIn("Agent loop", context.contextualized_query)

    def test_stable_memory_filter_does_not_store_unstructured_turn(self):
        service = ResearchMemoryService(self.db, settings(), FakeRedisMemory())
        result = final_result(task("What about this?", []))
        service.update(self.user.id, "session-a", "turn-a", result.query, result)
        self.assertEqual(self.db.query(ResearchLongTermMemory).count(), 0)

    def test_memory_update_persists_l1_summary(self):
        redis = FakeRedisMemory()
        service = ResearchMemoryService(self.db, settings(), redis)
        result = final_result()
        service.update(self.user.id, "session-a", "turn-a", result.query, result)
        self.assertEqual(len(redis.messages["session-a"]), 2)
        self.assertTrue(redis.summaries["session-a"])
        self.assertEqual(
            self.db.query(ChatMessage).filter(ChatMessage.session_id == self.sessions["session-a"].id).count(),
            2,
        )


class RuntimeMemoryTests(MemoryTestBase):
    def test_context_artifact_handoff_and_post_final_update(self):
        redis = FakeRedisMemory()
        redis.messages["session-a"] = [AiMessage(role="user", content="Example Agent action loop")]
        memory = ResearchMemoryService(self.db, settings(), redis)
        seen = {}

        class Analyzer:
            def analyze(self, query):
                seen["query"] = query
                return task(query, ["Example Agent"])

        class Researcher:
            def research(self, research_task):
                return final_result(research_task).evidence_pool

        class Drafter:
            def generate(self, research_task, pool):
                return final_result(research_task).draft

        class Verifier:
            def verify(self, research_task, draft, pool):
                return EvidenceVerificationResult(sufficient=True, supported_points=[draft.claims[0].text])

        runtime = ResearchEventDrivenRuntime(Analyzer(), Researcher(), Drafter(), Verifier(), settings(), memory)
        run = runtime.run(
            "How does it affect the next turn?",
            user_id=self.user.id,
            session_id="session-a",
        )
        context = run.board.latest_artifact("conversation_context").payload["value"]
        self.assertIn("Example Agent", context.contextualized_query)
        self.assertEqual(seen["query"], context.contextualized_query)
        self.assertIsNotNone(run.board.latest_artifact("memory_update"))
        self.assertIsNotNone(run.final_result)
        self.assertEqual(len(redis.messages["session-a"]), 3)

    def test_legacy_runtime_is_unaffected(self):
        self.assertEqual(EventDrivenAgentRuntimeService.framework_name, "event_driven_multi_agent")


if __name__ == "__main__":
    unittest.main()
